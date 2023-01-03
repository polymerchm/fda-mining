import sqlalchemy
import argparse
import requests
import sys
from zipfile import ZipFile
import os
from functools import reduce



parser = argparse.ArgumentParser(prog='buildDatabases', 
                                 description='Construct or update the databases')
parser.add_argument('-u', '--update', action='store_true')
args = parser.parse_args()



PRODUCT_CODE_FILE = 'data/foiclass.dat' #updated every sunday by FDA
PRODUCT_CODE_FILE_ZIP = 'data/foiclass.zip'
PRODUCT_CODE_FILE_URL = 'https://www.accessdata.fda.gov/premarket/ftparea/foiclass.zip'
ADVISORY_PANEL_FILE = 'data/advisory_panel.dat'
PRODUCT_DATABASE_FILE = 'data/product.db'
PANEL_DATABASE_FILE = 'data/panel.db'

if args.update:
    r = requests.get(PRODUCT_CODE_FILE_URL)
    if r.status_code >= 300:
        print('could not retrieve the product code file')
        sys.exit(1)
    with open(PRODUCT_CODE_FILE_ZIP, 'wb') as pFH:
        pFH.writelines(r.content)
    with ZipFile(PRODUCT_CODE_FILE_ZIP, 'rb') as zObj:
        zObj.extractall('data')
        
    if os.path.exists('data/foiclass.txt'):
        os.rename('data/foiclass.txt', PRODUCT_CODE_FILE)
        
with open(PRODUCT_CODE_FILE) as pc:
    products = pc.readlines()
    
with open(ADVISORY_PANEL_FILE) as ap:
    panels = ap.readlines()
    
    # build the product code database
products_split = [x.split('|') for x in products]

# check for consistent field count
minFields = 9999
maxFields = 0

minFields = reduce(lambda x,y: min(x,len(y)), 999 )
maxFields = reduce(lambda x,y: max(x, len(y)), 0)
    
print(minFields, maxFields)

    