import requests
from bs4 import NavigableString, BeautifulSoup
import re
import os, sys
from tempfile import TemporaryDirectory
from pathlib import Path
import time
from fuzzywuzzy import fuzz


import pytesseract
import fitz
from PIL import Image

AM_words = [
'additive',
'additively',
'additive manufactured',
'additive manufacturing',
'3d printing',
'3d printed',
'stereolithography',
'stereolithographic',
'powder fusion',
'powder bed fusion',
'FDM',
'FFF',
'SLS',
"DLP",
"SLA",
"laser sintering"
]


OFDA_DEVICE = 'https://api.fda.gov/device'
OFDA_510K = '/510k.json?'
OFDA_CLASSIFICATION = '/classification.json?'
OFDA_REGISTRATION = '/registrationlisting.json?'
OFDA_PMA = '/pma.json?'
SEARCH = 'search='
COUNT = 'count='
HAS_SUMMARY = 'statement_or_summary=Summary'
PDF_FOLDER = 'pdf/'

BASE_510K_URL = 'https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm?ID='

limit=10

if not os.path.exists(PDF_FOLDER):
    os.mkdir(PDF_FOLDER)
    
r = requests.get(f'{OFDA_DEVICE + OFDA_510K + SEARCH  + HAS_SUMMARY}&limit={limit}')

hits = r.json()['results']

meta = r.json()['meta']
if ('link' in r.headers):
    print (r.headers['link'])

for hit in hits:   
    k_number = hit['k_number']
    pdf_type = hit.get('statement_or_summary', 'missing')
    if pdf_type !='missing':
        r_510K = requests.get(f'{BASE_510K_URL}{k_number}')
        soup = BeautifulSoup(r_510K.text, 'lxml')
        summary_button = soup("a", text=re.compile(r'Summary'))
        if len(summary_button) == 0:
            continue
        elem = summary_button[0]
        pdf_url = elem.get('href', "")
        if pdf_url == "":
            continue
        else:    
            dataPath = os.path.join(PDF_FOLDER,k_number)
            if not os.path.exists(dataPath):        
                os.mkdir(dataPath)
            response = requests.get(pdf_url)
            pdfPath = os.path.join(dataPath,f"{k_number}.pdf")
            pdf = open(pdfPath, 'wb') 
            pdf.write(response.content)
            pdf.close()
            
# Store all the pages of the PDF in a variable
        image_file_list = []

        text_file = os.path.join(dataPath,'out_text.txt')


        with TemporaryDirectory() as tempdir:
    # Create a temporary directory to hold our temporary images.

            """
            Part #1 : Converting PDF to images
            """

            pdf_pages = fitz.open(pdfPath)
        # Read in the PDF file at 500 DPI

        # Iterate through all the pages stored above
            print(f'File {k_number} {len(pdf_pages)} pages, processing time =',end='')
            start = time.time()
            for page_enumeration, page in enumerate(pdf_pages, start=1):
                filename = os.path.join(tempdir,f'page_{page_enumeration:03}.jpg')
                pix = page.get_pixmap(dpi=300)
                pix.save(filename)
                image_file_list.append(filename)

            """
            Part #2 - Recognizing text from the images using OCR
            """

            with open(text_file, "a") as output_file:
                for image_file in image_file_list:
                    text = str(((pytesseract.image_to_string(Image.open(image_file)))))
                    text = text.replace("-\n", "")
                    output_file.write(text)
                    
            end = time.time()
            print(f' {(end - start):.0f} seconds')
            
            # use fuzz package to search for terms in the list and deal with incorrect OCR
  
            with open(text_file) as input_file:
                lines = input_file.read()
                for item in AM_words:
                    ratio = fuzz.partial_ratio(item.lower(), lines.lower())              
                    if ratio > 80:  
                        print(item, ratio) 
        pass





