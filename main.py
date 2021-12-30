import ebooklib
from ebooklib import epub
from w3lib.html import replace_entities # works!
from html.parser import HTMLParser
import pprint
import json
import os
import re
from difflib import SequenceMatcher

MARANATHA_URLS = 'es_MSV76_urls.json'
MARANATHA_FILE_IDS = 'es_MSV76_file_ids.json'
CS_URLS = 'es_CS_urls.json'
CS_FILE_IDS = 'es_CS_file_ids.json'

URLS = 'es_AFC_urls.json'
FILE_IDS = 'es_AFC_file_ids.json'

# FILE_NAME = 'es_MSV76.epub'
# FORMATTED_FILE = 'es_MSV76.json'
# FILE_NAME = 'es_RP.epub'
# FORMATTED_FILE = 'es_RP.json'
FILE_NAME = 'es_AFC.epub'
FORMATTED_FILE = 'es_AFC.json'
# FILE_NAME = 'es_CT.epub'
# FORMATTED_FILE = 'es_CT.json'

# completely ignored
IGNORED_TAGS = ['html', 'head', 'body']
# selectively ignored
IGNORED_TAG_CLASS = [('div', 'chapter'), ('hr', 'footnote'), ('p', 'center'), ('span', 'pagebreak'), ('h1', 'sectionhead'),
                     ('sup', 'bookendnote'), ('a', 'bookendnote'), ('span', 'bookendnote'), ('sup', None)]

MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

TITLE, VERSE, VERSE_REF, PARAGRAPH, POEM, POEM_BR, FOOTNOTE_REF, FOOTNOTE, WRITE_DATA, BOOK_REF, BOOK_REF_IBID, EGW_REF, IGNORE_ALL = range(13)


class EGWDevotionalEpubParser(HTMLParser):
    def __init__(self, devotional = {}, states = [], paragraphs_count=0):
        super().__init__()
        self.devotional = devotional
        self.states = states
        self.paragraphs_count = paragraphs_count

    def handle_starttag(self, tag, attrs):
        sclass = self._get_class(attrs)
        if tag == 'h2' and sclass == 'chapterhead':
            self.states.append(TITLE)
        elif tag == 'p' and sclass == 'devotionaltext':
            self.states.append(VERSE)
        elif tag == 'span' and sclass == 'bible-spa':
            self.states.append(VERSE_REF)
        elif tag == 'p' and sclass == 'standard-indented':
            self.states.append(PARAGRAPH)
        elif tag == 'p' and sclass == 'standard-noindent':
            self.states.append(PARAGRAPH)
        elif tag == 'p' and sclass == 'poem-noindent':
            self.states.append(POEM)
        elif tag == 'br' and self.states[-1] == POEM:
            self.states.append(POEM_BR)
        elif tag == 'sup' and sclass == 'footnote':
            self.states.append(FOOTNOTE_REF)
        elif tag == 'p' and sclass == 'footnote':
            self.states.append(FOOTNOTE)
        elif tag == 'a' and sclass == 'footnote':
            self.states.append(WRITE_DATA)
        elif tag == 'em':
            self.states.append(BOOK_REF)
        elif tag == 'span' and sclass == 'nol-ink':
            self.states.append(BOOK_REF_IBID)
        elif tag == 'span' and (sclass == 'egw-spa' or sclass == 'egw-eng'):
            self.states.append(EGW_REF)
        elif tag == 'span' and sclass == 'non-egw-comment':
            self.states.append(WRITE_DATA)
        elif tag == 'strong':
            self.states.append(WRITE_DATA)
        elif self._ignored_staff(tag, attrs):
            self.states.append(IGNORE_ALL)
        else:
            raise Exception(f'Unknown tag: {tag}, attrs: {attrs}')


    def handle_endtag(self, tag):
        # if len(self.states) > 1 and self.states[-1] == IGNORE_ALL and self.states[-2] == BOOK_REF_IBID:
        #     self.devotional['paragraphs'][str(self.paragraphs_count+1)] = self.devotional['paragraphs'][str(self.paragraphs_count+1)][:-1]
        if self.states[-1] in [PARAGRAPH, POEM, FOOTNOTE]:
            self.paragraphs_count += 1
        self.states.pop()


    def handle_data(self, data):
        # avoid weird staff
        data = self._handleable_data(data)
        if data != None:
            if self.states[-1] == TITLE:
                self.devotional['title_date'] = data
                sdata = data.rsplit(',', 1)
                self.devotional['title'] = sdata[0].strip()
                self.devotional['date'] = sdata[1].strip()
                ndate = get_day_month(self.devotional['date'])
                self.devotional['month'] = int(ndate[0])
                self.devotional['day'] = int(ndate[1])
            elif self.states[-1] == VERSE:
                self._append_data(VERSE, data)
            elif self.states[-1] == VERSE_REF:
                if len(self.states) > 1 and self.states[-2] == PARAGRAPH:
                    self.devotional['paragraphs'][self.paragraphs_count] += (' ('+data+')')
                else:
                    self.devotional['verse'] += (' ('+data+')')
            elif self.states[-1] == PARAGRAPH:
                self._append_data(PARAGRAPH, data)
            elif self.states[-1] == POEM:
                self._append_data(POEM_BR, data)
            elif self.states[-1] == POEM_BR:
                self._append_data(POEM_BR, data)
            # footnote reference in paragraph
            elif len(self.states) > 2 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE_REF and self.states[-3] == PARAGRAPH:
                self.devotional['paragraphs'][self.paragraphs_count] += ('('+data+') ')
            # paragraph with footnote reference
            elif len(self.states) > 2 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE_REF and self.states[-3] == FOOTNOTE:
                self._append_data(FOOTNOTE, data)
            elif self.states[-1] == FOOTNOTE:
                self.devotional['paragraphs'][self.paragraphs_count] += data
            elif self.states[-1] == BOOK_REF_IBID:
                self.devotional['paragraphs'][self.paragraphs_count] += ('('+data+')')
            elif self.states[-1] == BOOK_REF:
                self.devotional['paragraphs'][self.paragraphs_count] += (' '+data+' ')
            elif self.states[-1] == EGW_REF:
                self.devotional['paragraphs'][self.paragraphs_count] += (' ('+data+')')
            elif len(self.states) > 1 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE:
                self.devotional['paragraphs'][self.paragraphs_count] += data
            
                
    def dumps(self):
        if self.devotional != {}:
            self.devotional['paragraphs_count'] = self.paragraphs_count
            self.devotional['urls'] = {
                "YouTube" : self._get_url(self.devotional['month'], self.devotional['day'])
            }
            self.devotional['telegram_file_ids'] = {
                "mp3" : self._get_file_id(self.devotional['month'], self.devotional['day'])
            }
            return json.dumps(self.devotional, ensure_ascii=False, indent = 2, separators=(',', ': '))
        else:
            return ''

    def _get_class(self, attrs):
        for a in attrs:
            if a[0] == 'class':
                return a[1]
        return None

    def _ignored_staff(self, tag, attrs):
        if tag in IGNORED_TAGS:
            return True
        for tc in IGNORED_TAG_CLASS:
            if tc[0] == tag and tc[1] == self._get_class(attrs):
                return True
        return False

    def _handleable_data(self, data):
        data = data.strip()
        if data == '':
            return None
        else:
            return data

    def _append_data(self, state, data):
        if state == VERSE:
            if not 'verse' in self.devotional:
                self.devotional['verse'] = data
            else:
                self.devotional['verse'] += data
        elif state == PARAGRAPH:
            if not 'paragraphs' in self.devotional:
                self.devotional['paragraphs'] = []
            if has_index(self.paragraphs_count, self.devotional['paragraphs']):
                self.devotional['paragraphs'][self.paragraphs_count] += data
            else:
                self.devotional['paragraphs'].append(data)
        elif state == POEM:
            if not 'paragraphs' in self.devotional:
                self.devotional['paragraphs'] = []
            if has_index(self.paragraphs_count, self.devotional['paragraphs']):
                self.devotional['paragraphs'][self.paragraphs_count] += data
            else:
                self.devotional['paragraphs'].append(data)
        elif state == POEM_BR:
            if not 'paragraphs' in self.devotional:
                self.devotional['paragraphs'] = []
            if has_index(self.paragraphs_count, self.devotional['paragraphs']):
                self.devotional['paragraphs'][self.paragraphs_count] += (data + '\n')
            else:
                self.devotional['paragraphs'].append(data + '\n')
        elif state == FOOTNOTE:
            if has_index(self.paragraphs_count, self.devotional['paragraphs']):
                self.devotional['paragraphs'][self.paragraphs_count] += ('('+data+') ')
            else:
                self.devotional['paragraphs'].append('('+data+') ')
    
    def _get_url(self, month, day):
        links = {}
        with open(URLS, 'rb') as fp:
            links = json.load(fp)
        for k, v in links.items():
            if v['day'] == str(day) and v['month'] == str(month):
                return v['url']
        return None
    
    def _get_file_id(self, month, day):
        file_ids = {}
        id_list = []
        with open(FILE_IDS, 'rb') as fp:
            file_ids = json.load(fp)
        for fid in file_ids:
            if fid['day'] == str(day) and fid['month'] == str(month):
                id_list.append(fid['file_id'])
        return id_list

    
def has_index(index, list):
    return (0 <= index) and (index < len(list))




















class EGWBookEpubParser(HTMLParser):
    def __init__(self, chapter = {}, states = [], paragraphs_count=0):
        super().__init__()
        self.chapter = chapter
        self.states = states
        self.paragraphs_count = paragraphs_count

    def handle_starttag(self, tag, attrs):
        sclass = self._get_class(attrs)
        if tag == 'h2' and sclass == 'chapterhead':
            self.states.append(TITLE)
        elif tag == 'span' and sclass == 'bible-spa':
            self.states.append(VERSE_REF)
        elif tag == 'p' and sclass == 'standard-indented':
            self.states.append(PARAGRAPH)
        elif tag == 'p' and sclass == 'standard-noindent':
            self.states.append(PARAGRAPH)
        elif tag == 'p' and sclass == 'poem-noindent':
            self.states.append(POEM)
        elif tag == 'br' and self.states[-1] == POEM:
            self.states.append(POEM_BR)
        elif tag == 'sup' and sclass == 'footnote':
            self.states.append(FOOTNOTE_REF)
        elif tag == 'p' and sclass == 'footnote':
            self.states.append(FOOTNOTE)
            # raise Exception('footnote found')
        elif tag == 'a' and sclass == 'footnote':
            self.states.append(WRITE_DATA)
        elif tag == 'em':
            self.states.append(BOOK_REF)
        elif tag == 'span' and sclass == 'nol-ink':
            self.states.append(BOOK_REF_IBID)
        elif tag == 'span' and (sclass == 'egw-spa' or sclass == 'egw-eng'):
            self.states.append(EGW_REF)
        elif tag == 'span' and sclass == 'non-egw-comment':
            self.states.append(WRITE_DATA)
        elif tag == 'span' and sclass == 'non-egw-appendix':
            self.states.append(WRITE_DATA)
        elif tag == 'span' and sclass == 'underline':
            self.states.append(WRITE_DATA)
        elif tag == 'strong':
            self.states.append(WRITE_DATA)
        elif self._ignored_staff(tag, attrs):
            self.states.append(IGNORE_ALL)
        else:
            raise Exception(f'Unknown tag: {tag}, attrs: {attrs}')


    def handle_endtag(self, tag):
        if self.states[-1] in [PARAGRAPH, POEM, FOOTNOTE]:
            self.paragraphs_count += 1
        self.states.pop()


    def handle_data(self, data):
        # avoid weird staff
        data = self._handleable_data(data)
        if data != None:
            if self.states[-1] == TITLE:
                self.chapter['chapter_number'] = int(data.split('—')[0].split(' ')[1])
                self.chapter['chapter_title'] = data.split('—')[1]
            elif self.states[-1] == VERSE_REF:
                if len(self.states) > 1 and self.states[-2] == PARAGRAPH:
                    if self.chapter['paragraphs'][self.paragraphs_count][-1] == '(':
                        self.chapter['paragraphs'][self.paragraphs_count] += data
                    else:
                        self.chapter['paragraphs'][self.paragraphs_count] += (' '+data)
                else:
                    self.chapter['paragraphs'][self.paragraphs_count] += (' '+data)
            elif self.states[-1] == PARAGRAPH:
                self._append_data(PARAGRAPH, data)
            elif self.states[-1] == POEM:
                self._append_data(POEM_BR, data)
            elif self.states[-1] == POEM_BR:
                self._append_data(POEM_BR, data)
            # footnote reference in paragraph
            elif len(self.states) > 2 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE_REF and self.states[-3] == PARAGRAPH:
                self.chapter['paragraphs'][self.paragraphs_count] += ('('+data+') ')
            # paragraph with footnote reference
            elif len(self.states) > 2 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE_REF and self.states[-3] == FOOTNOTE:
                self._append_data(FOOTNOTE, data)
            elif self.states[-1] == FOOTNOTE:
                self.chapter['paragraphs'][self.paragraphs_count] += data
            elif self.states[-1] == BOOK_REF_IBID:
                self.chapter['paragraphs'][self.paragraphs_count] += ('('+data+')')
            elif self.states[-1] == BOOK_REF:
                if 'paragraphs' not in self.chapter:
                    self.chapter['paragraphs'] = []
                if has_index(self.paragraphs_count, self.chapter['paragraphs']):
                    self.chapter['paragraphs'][self.paragraphs_count] += data
                else:
                    self.chapter['paragraphs'].append(data)
            elif self.states[-1] == EGW_REF:
                self.chapter['paragraphs'][self.paragraphs_count] += (' ('+data+')')
            elif len(self.states) > 1 and self.states[-1] == WRITE_DATA and self.states[-2] == FOOTNOTE:
                self.chapter['paragraphs'][self.paragraphs_count] += data
            
                
    def dumps(self):
        if self.chapter != {}:
            self.chapter['paragraphs_count'] = self.paragraphs_count
            self.chapter['urls'] = {
                'YouTube' : self._get_url(self.chapter['chapter_number'])
            }
            self.chapter['telegram_file_ids'] = {
                'mp3' : self._get_file_id(self.chapter['chapter_number'])
            }
            return json.dumps(self.chapter, ensure_ascii=False, indent = 2, separators=(',', ': '))
        else:
            return ''

    def _get_class(self, attrs):
        for a in attrs:
            if a[0] == 'class':
                return a[1]
        return None

    def _ignored_staff(self, tag, attrs):
        if tag in IGNORED_TAGS:
            return True
        for tc in IGNORED_TAG_CLASS:
            if tc[0] == tag and tc[1] == self._get_class(attrs):
                return True
        return False

    def _handleable_data(self, data):
        data = data.strip()
        if data == '':
            return None
        else:
            return data

    def _append_data(self, state, data):
        if state == VERSE:
            if not 'verse' in self.chapter:
                self.chapter['verse'] = data
            else:
                self.chapter['verse'] += data
        elif state == PARAGRAPH:
            if not 'paragraphs' in self.chapter:
                self.chapter['paragraphs'] = []
            if has_index(self.paragraphs_count, self.chapter['paragraphs']):
                self.chapter['paragraphs'][self.paragraphs_count] += data
            else:
                self.chapter['paragraphs'].append(data)
        elif state == POEM:
            if not 'paragraphs' in self.chapter:
                self.chapter['paragraphs'] = []
            if has_index(self.paragraphs_count, self.chapter['paragraphs']):
                self.chapter['paragraphs'][self.paragraphs_count] += data
            else:
                self.chapter['paragraphs'].append(data)
        elif state == POEM_BR:
            if not 'paragraphs' in self.chapter:
                self.chapter['paragraphs'] = []
            if has_index(self.paragraphs_count, self.chapter['paragraphs']):
                self.chapter['paragraphs'][self.paragraphs_count] += (data + '\n')
            else:
                self.chapter['paragraphs'].append(data + '\n')
        elif state == FOOTNOTE:
            if has_index(self.paragraphs_count, self.chapter['paragraphs']):
                self.chapter['paragraphs'][self.paragraphs_count] += ('('+data+') ')
            else:
                self.chapter['paragraphs'].append('('+data+') ')
    
    def _get_url(self, chapter):
        links = {}
        with open(CS_URLS, 'rb') as fp:
            links = json.load(fp)
        for k, v in links.items():
            if v['chapter'] == f'Capítulo {chapter}':
                return v['url']
        return None
    
    def _get_file_id(self, chapter):
        file_ids = {}
        id_list = []
        with open(CS_FILE_IDS, 'rb') as fp:
            file_ids = json.load(fp)
        for fid in file_ids:
            if fid['chapter'] == f'Capítulo {chapter}':
                id_list.append(fid['file_id'])
        return id_list



class MyHTMLXRay(HTMLParser):
    def handle_starttag(self, tag, attrs):
        print("Encountered a start tag:", tag, ' attrs: ', attrs)

    def handle_endtag(self, tag):
        print("Encountered an end tag :", tag)

    def handle_data(self, data):
        print("Encountered some data  :", data)

def get_day_month(date):
    day = re.findall(r'\d+', date)
    day = ''.join(day)

    try:
        month = str(MONTHS.index(date.rsplit(' ', 1)[1])+1)
    except ValueError:
        # on typo -> similarity-based work around
        ratios = [SequenceMatcher(None, date.rsplit(' ', 1)[1], m).ratio() for m in MONTHS]
        month = str(ratios.index(max(ratios))+1)
    return (month, day)

def xray_doc():
    parser = MyHTMLXRay()
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())
    print(its)

def xray_item(item):
    parser = MyHTMLXRay()
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())
    i = its[item].get_content()
    parser.feed(replace_entities(i))

def process_item_print(item):
    parser = EGWDevotionalEpubParser()
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())
    i = its[item].get_content()
    parser.feed(replace_entities(i))
    print(parser.dumps())

def process_book_item_print(item):
    parser = EGWBookEpubParser()
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())
    i = its[item].get_content()
    parser.feed(replace_entities(i))
    print(parser.dumps())

def process_full_write():
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())

    with open(FORMATTED_FILE, 'wb+') as f:
        # f.write('{\n')
        jsonfile = []
        idx = 1
        enum = 10
        for it in its[enum:386]:
            parser = EGWDevotionalEpubParser({}, [], 0)
            parser.feed(replace_entities(it.get_content()))
            towrite = parser.dumps()
            if towrite != '':
                jsonfile.append(parser.devotional)
                idx += 1
                # f.write(towrite)
                # print('i = ', idx+10-1)
                # f.write(',\n')
            enum += 1
            print(enum)
        f.write(json.dumps(jsonfile, ensure_ascii=False, indent = 2, separators=(',', ': ')).encode('utf-8'))
    
def process_full_book_write():
    book = epub.read_epub(FILE_NAME)
    its = list(book.get_items())

    with open(FORMATTED_FILE, 'wb+') as f:
        # f.write('{\n')
        jsonfile = []
        idx = 1
        enum = 10
        for it in its[10:53]:
            parser = EGWBookEpubParser({}, [], 0)
            parser.feed(replace_entities(it.get_content()))
            towrite = parser.dumps()
            if towrite != '':
                jsonfile.append(parser.chapter)
                idx += 1
                # f.write(towrite)
                # print('i = ', idx+10-1)
                # f.write(',\n')
            print(enum)
            enum += 1
        f.write(json.dumps(jsonfile, ensure_ascii=False, indent = 2, separators=(',', ': ')).encode('utf-8'))

    # with open(FORMATTED_FILE, 'rb+') as filehandle:
    #     filehandle.seek(-1, os.SEEK_END)
    #     filehandle.truncate()

    # with open(FORMATTED_FILE, 'a+') as f:
    #     f.write('}')

if __name__ == '__main__':
    # xray_doc()
    # xray_item(385)
    # process_book_item_print(52)
    # process_item_print(386)
    process_full_write()
    # process_full_book_write()