import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from signal import SIGINT, SIGTERM, signal
from tempfile import TemporaryDirectory

import fitz
import pytesseract
import requests
from bs4 import BeautifulSoup, NavigableString
from fuzzywuzzy import fuzz, process
from PIL import Image

from smart_open import smart_open

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

BE_Words = [
    'bioabsorbable',
    'resorbable',
    'biodegradable',
    'absorbable'
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

default_limit=500

killed = False

def catchSIGINT(signum,frame):
    global killed
    print('SIGINT received.   Will Stop after this cycle')
    killed = True

def main(): 
    signal(SIGINT, catchSIGINT)
    # check to see if this is a restart
    parser = argparse.ArgumentParser(
        prog="fda-miner",
        description='This program deep earches the FDA 510(k) database'
    )
    parser.add_argument('-v', '--verbose', action='store_true', help='extra output')
    parser.add_argument('-r', '--restart', action='store_true', help='start over if the restart_url file is present')
    parser.add_argument('-l', '--limit',   action='store', default=default_limit, help='set number of hits maximum')
    parser.add_argument('-o', '--output', action='store', default='stdout', help='file to output to')
    parser.add_argument('-a', '--append', action='store_true', help='if output file not stdout, append to the file rather tan a new one')
    args = parser.parse_args()
    
    LOGGER = logging.getLogger('fda')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    
    restart_url = None
    if os.path.exists('restart_url.txt') and args.restart:
        LOGGER.debug('restart mode')          
        with open('restart_url.txt') as fd:
            restart_url = fd.readline()
            LOGGER.debug(f'Next url is {restart_url}')
            
    if not os.path.exists(PDF_FOLDER):
        LOGGER.debug('Creating main folder')
        os.mkdir(PDF_FOLDER)
        
    link = None    
        
    # initial search 
    while True:
        if killed:
            print("Exiting.   Use restart and append to continue")
            sys.exit(0)
            
        if  restart_url:
            r = requests.get(restart_url)
        else:
            r = requests.get(f'{OFDA_DEVICE + OFDA_510K + SEARCH  + HAS_SUMMARY}&limit={args.limit}')
    
        hits = r.json()['results']

        if ('link' in r.headers):
            match = re.search("\<(.*)\>", r.headers['link'])
            if match:
                link = match.groups()[0]
                with open('restart_url.txt', 'w') as fd:
                    fd.write(link)
            
        out_file = (args.output if args.output != 'stdout' else '-').strip()
        with smart_open(out_file, append=args.append, buffering=1) as textFH:
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
                        start = time.time()
                        for page_enumeration, page in enumerate(pdf_pages, start=1):
                            filename = os.path.join(tempdir,f'page_{page_enumeration:03}.jpg')
                            pix = page.get_pixmap(dpi=300)
                            pix.save(filename)
                            image_file_list.append(filename)
                        os.remove(pdfPath)  # erase the pdf file for space saving
            
                        
                        with open(text_file, "a") as output_file:
                            for image_file in image_file_list:
                                    text = str(((pytesseract.image_to_string(Image.open(image_file)))))
                                    text = text.replace("-\n", "")
                                    output_file.write(text)
                                    
                            end = time.time()
                            print(f'File {k_number} {len(pdf_pages)} pages, processing time is {(end - start):.0f} seconds')
                            
                            # use fuzz package to search for terms in the list and deal with incorrect OCR
                            isFileHeaderOutput = False
                            with open(text_file) as input_file:
                                lines = input_file.read()
                                for item in BE_Words:
                                    ratio = fuzz.partial_ratio(item.lower(), lines.lower())              
                                    if ratio > 80:  
                                        if not isFileHeaderOutput:
                                            textFH.write(f'File {k_number} {len(pdf_pages)} pages\n')        
                                            textFH.write(f"    Product Code = {hit['product_code']}\n")
                                            textFH.write(f"    Device name = {hit['device_name']}\n")   
                                            isFileHeaderOutput = True
                                        textFH.write(    f"        Has {item} with ratio {ratio}\n") 
                    

if __name__ == '__main__':
    main()




