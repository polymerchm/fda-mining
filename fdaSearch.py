import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
import json
import shutil
from collections import defaultdict
# from models import PanelModel, DeviceModel, session, base, engine
import sqlite3


from fuzzywuzzy import fuzz
from smart_open import smart_open

searchTermGroups = {  # lead ! mean not, lead 
    'AM' : [
        'additive',
        'additively',
        'additive manufactured',
        'additive manufacturing',
        '3d print',
        'stereolithography',
        'stereolithographic',
        'powder fusion',
        'powder bed fusion',
        'fdm',
        'fff',
        'slf',
        "dlp",
        "sla",
        "laser sintering",
        # "!metal",
        # "!alloy"
    ],

    'BE' : [
        'bioabsorbable',
        'resorbable',
        'biodegradable',
        'absorbable',
        '!suture',
        '!nondegradable',
        '!non degradable',
        '!nonabsorbable',
        '!non absorbable'
    ]
}


PDF_FOLDER = 'pdf/'

IGNORE_TAGS = {"registration_number","fei_number"}

BASE_DIR = os.path.dirname(os.path.abspath(__name__))
DB_URI = "sqlite:///" + os.path.join(BASE_DIR, 'fda.db')

    
def getYear(k):
    match = re.search('K(\d\d)\d{4}',k)
    twoDigits = match.groups()[0]
    return ('19' if int(twoDigits) > 75 else '20') + twoDigits

def loadSearchFile(filename):
    return []
    
def convert2json(data):
    with open(data) as df:
        lines = [x.strip('\n') for x in df.readlines()]
    
    outString = '{'
    for i in range(4,len(lines)):
        line = lines[i]
        if ':' in line:
            tag = line.split(':')[0]
            cleaned_tag = tag.strip('\'\" ')

            if  cleaned_tag in IGNORE_TAGS:
                continue
            if cleaned_tag == "device_class":   
                lines[i] = line.strip(',')
        outString += lines[i].strip()
    # outString += '}'
    return outString

def main(): 

    cnx = sqlite3.connect( 'fda.db')
    cursor = cnx.cursor()

    #check to see if this is a restart
    parser = argparse.ArgumentParser(
        prog="fda-miner",
        description='This program deep earches the FDA 510(k) database'
    )
    parser.add_argument('-v', '--verbose', action='store_true', default=False, help='extra output')
    parser.add_argument('-o', '--output', action='store', default='-', help='file to output to')
    parser.add_argument('-f', '--file', action='store', default='none', help='file to get words from')
    parser.add_argument('-s', '--search', action='store', default='none', help='key for search term groups' )
    parser.add_argument('-p', '--purge', action='store_true', default=False, help='purge empry folders')
    parser.add_argument('-c', '--cutoff', action='store', default=80, help='cutoff value')
    parser.add_argument('--sortby', action='store', default='k_number', help='how to sort the final output')
    args = parser.parse_args()
    
   
    
    LOGGER = logging.getLogger('fda_search')
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    if not os.path.exists(PDF_FOLDER):
        LOGGER.error(f"Cant find the folder {PDF_FOLDER}")
        sys.exit(1)
        
    if args.search != 'none' and args.file != 'none':
        LOGGER.error(" Cannot have both file and search parameters")
        sys.exit(1)
        
    if args.search != 'none':
        search_list = searchTermGroups.get(args.search, [])
        if len(search_list) == 0:
            LOGGER.error(f"Search type {args.search} not valid key")
            sys.exit(1)
    else:
        # read them form the file
        if not os.path.exists(args.fiile):
            LOGGER.error(f"Search terms file  {args.file} not found")
            sys.exit(1)
        with open(args.file) as sfd:
            lines = sfd.readlines(sfd)
        if len(lines) == 0:
            LOGGER.error(f"Search terms file  {args.file} is empty")
            sys.exit(1)
        search_list = [x.trim() for x in lines]
        
            
    output_file,_ = os.path.splitext(args.output)

    number_empty = 0
    total_k = 0
    negative_hits = 0
    found_510Ks = [] # an array of device objects that are positive hits
    count_by_product_code = defaultdict(int)
    
    for root, dirs, files in os.walk(PDF_FOLDER):
        if root.startswith(PDF_FOLDER) and re.match("K\d{6}",os.path.split(root)[1]):
            if len(files) != 2:
                if args.purge:
                    shutil.rmtree(root)
                number_empty += 1
                continue
            else:
                total_k += 1
                k_number = os.path.basename(root)
                ocrTextFilename = os.path.join(root,'out_text.txt') 
                dataFilename =  os.path.join(root,'data.txt')    
                json_string = convert2json(dataFilename)
                try:
                    device_dict = json.loads(json_string)
                except json.JSONDecodeError as e:
                    x = 1
                    LOGGER.error(f'Cannot parse {k_number} json string {e}')
                    LOGGER.error(f"{e.doc[e.colno-20:e.colno+20]}")
                    continue


                #  text for skips in device type
                
                try:
                    device_name = device_dict['openfda']['device_name'].lower()
                except:
                    device_name = "missing"
                wasMatched = False
                for item in search_list:
                    if item.startswith('!'):
                        search_field = item[1:]
                        if re.search(search_field, device_name):
                            wasMatched = True
                            LOGGER.info(f"{k_number} negated device name {device_name} by {search_field}")
                            break
                if wasMatched:
                    negative_hits +=  1
                    continue # ignore this device
                
                            



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
                        device_dict['predicates'] = predicates

                    hit_list = [] 
                    clearList = False
                    for item in search_list:
                        search_term = item[1:] if item.startswith('!') else item
                        ratio = fuzz.partial_ratio(search_term.lower(), lines.lower())              
                        if ratio > int(args.cutoff):
                            if item.startswith('!'):   #not this
                                LOGGER.info(f"{k_number} content negated by {search_field}") 
                                negative_hits += 1
                                clearList = True
                                break
                            else:
                                hit_list.append([item, ratio])

                    if  clearList:
                        hit_list = []
                    if len(hit_list) > 0:
                        LOGGER.info(f'File {k_number}')        
                        LOGGER.info(f"    Product Code = {device_dict['product_code']}")
                        LOGGER.info(f"    Device name =  {device_name}")       
                        for item,ratio in hit_list:     
                            LOGGER.info(f"        Hit: {item},ratio: {ratio}")
                        device_dict['hits'] = hit_list
                        found_510Ks.append(device_dict)  
                        product_code = device_dict['product_code']
                        count_by_product_code[product_code] += 1
    
    if args.sortby in found_510Ks[0].keys():
        sortby = args.sortby
    else:
        sortby = 'k_number'
    
    found_510Ks.sort(key=lambda x: x[sortby])
    json_found = json.dumps(found_510Ks, indent=5)

    sorted_count_by_product_code = sorted(count_by_product_code.items(), key=lambda x:x[1])
    count_by_product_code = dict(sorted_count_by_product_code)

    
    json_out = "-" if output_file == "-" else output_file + '.json'
    with smart_open(json_out, "w") as fh:
        fh.write(json_found)

    

    dat_out = "-" if output_file == '_' else output_file + '.dat'        
    with smart_open(dat_out, "w") as fh:

        fh.write(f"Total folders scanned: {total_k}\n")
        fh.write(f"Number of hits is {len(found_510Ks)}\n")
        fh.write(f"NUmber discarded to negative hits {negative_hits}\n")
        if number_empty != 0:
            fh.write(f"There were {number_empty} empty folders\n\n")     
        fh.write(f"Count by product code\n")
    

    

        for key,value in count_by_product_code.items():
            cursor.execute(f"SELECT devicename FROM device WHERE productcode='{key}'")
            devicename = cursor.fetchall()
            fh.write(f"        Product code={key}: {value:04}  {devicename[0][0]}\n")

        cnx.close()
        

if __name__ == '__main__':
    main()




