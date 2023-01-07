import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import json

import fitz
import pytesseract
import requests
from bs4 import BeautifulSoup, NavigableString
from fuzzywuzzy import fuzz, process
from PIL import Image
import redis

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

stop_state_key = "STOPSTATE"
skip_count_key = "SKIPCOUNT"

default_limit=500

killed = False

def catchSIGINT(signum,frame):
    global killed
    print('SIGINT received.   Will Stop after this cycle')
    killed = True
    
    

def main(): 

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
    redisHandle = redis.Redis()
    redisHandle.set(stop_state_key ,'run')
    if redisHandle.get(skip_count_key) is None:
        redisHandle.set(skip_count_key, 0)
    limit = int(args.limit)
        
    # initial search 
    while True:
        status = redisHandle.get(stop_state_key).decode()
        if status != 'run':
            print("Exiting. Use restart and append to continue")
            sys.exit(0)
        skip_count = int(redisHandle.get(skip_count_key))   
        response = requests.get(f'{OFDA_DEVICE + OFDA_510K + SEARCH  + HAS_SUMMARY}&limit={limit}&skip={skip_count}')
        redisHandle.incrby(skip_count_key, limit)
    
        hits = response.json()['results']

        if ('link' in 'https://api.fda.gov/device/510k.json?search=statement_or_summary%3DSummary&limit=50&skip=0&search_after=0%3D-N0tbIUBMAeqG3hVbMy_'):
            match = re.search("\<(.*)\>", 'https://api.fda.gov/device/510k.json?search=statement_or_summary%3DSummary&limit=50&skip=0&search_after=0%3D-N0tbIUBMAeqG3hVbMy_')
            if match:
                link = match.groups()[0]
                with open('restart_url.txt', 'w') as fd:
                    fd.write(link)
                restart_url = link
            
        out_file = (args.output if args.output != 'stdout' else '-').strip()
        
        for hit in hits:   
            with smart_open(out_file, append=args.append, buffering=1) as hitTextOutput:
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
                        # metadata file
                        product_code = hit.get('product_code','???')
                        device_name = hit.get('device_name','no name')
                        advisory_committee = hit.get('advisory_committee', 'XX')
                        advisory_committee_desc = hit.get('advisory_committee_description', 'no description')
                        applicant = hit.get('applicant', 'no applicant')
                        all510Kfilaname = os.path.join(dataPath, 'data.txt')
                   
                        #get the summary pdf and save it
                        response = requests.get(pdf_url)
                        pdfPath = os.path.join(dataPath,f"{k_number}.pdf")
                        pdf = open(pdfPath, 'wb') 
                        pdf.write(response.content)
                        pdf.close()
                        
            # Store all the pages of the PDF in a variable
                    image_file_list = []

                    ocrTextFilename = os.path.join(dataPath,'out_text.txt')

                
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
            
                        
                        with open(ocrTextFilename, "a") as ocrOutput:
                            for image_file in image_file_list:
                                    text = str(((pytesseract.image_to_string(Image.open(image_file)))))
                                    text = text.replace("-\n", "")
                                    ocrOutput.write(text)
                                    
                        end = time.time()
                        print(f'File {k_number} {len(pdf_pages)} pages, processing time is {(end - start):.0f} seconds')
                        
                        # use fuzz package to search for terms in the list and deal with incorrect OCR
                        isFileHeaderOutput = False
                        with open(ocrTextFilename) as ocrInput:
                            lines = ocrInput.read()
                            # look for predicate information'
                            results = re.findall(r'K\d{6}',lines)
                            predicates = None
                            if results and len(results) != 0:
                                all = set([x.strip() for x in results])
                                all.discard(k_number)
                                predicates = list(all)
                                if predicates and len(predicates) != 0:
                                   hit['predicates'] = predicates
                            
                            for item in BE_Words:
                                ratio = fuzz.partial_ratio(item.lower(), lines.lower())              
                                if ratio > 80:  
                                    if not isFileHeaderOutput:
                                        hitTextOutput.write(f'File {k_number} {len(pdf_pages)} pages\n')        
                                        hitTextOutput.write(f"    Product Code = {hit['product_code']}\n")
                                        hitTextOutput.write(f"    Device name = {hit['device_name']}\n")       
                                        isFileHeaderOutput = True
                                    hitTextOutput.write(    f"        Has {item} with ratio {ratio}\n") 
                                    hitTextOutput.flush()
                                    
                            hit['openfda']['fei_number'] = 'see openFDA'
                            hit['openfda']['registration_number'] = 'see openFDA'   
                            with open(all510Kfilaname,'w') as all510KsFH:
                                all510KsFH.write(f'Product Code: {product_code}\n')
                                all510KsFH.write(f'Applicant:    {applicant}\n')
                                all510KsFH.write(f'Device Name:  {device_name}\n')
                                all510KsFH.write(f'Advisory Committee ({advisory_committee}): {advisory_committee_desc}')
                                all510KsFH.write(json.dumps(hit,indent=4))
                    

if __name__ == '__main__':
    main()




