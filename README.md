This Repository is an attempt to "deep" scrape the FDA CDRH website (here)[https://www.fda.gov/medical-devices/device-advice-comprehensive-regulatory-assistance/medical-device-databases] for keywords at the Summary Document Level

It uses (openFDA)[https://open.fda.gov/] to get 510(k) numbers, and then the CDRH website and (BeautifulSoup)[https://beautiful-soup-4.readthedocs.io/en/latest/#] to download individual PDFs of the summary documents.

Once downloaded, the PDFs are converted to images and using the (tesseract)[https://github.com/tesseract-ocr/tesseract] library, converted to serachable text

Text searches are from a keyword list using the (fuzzywuzzy) [https://www.geeksforgeeks.org/fuzzywuzzy-python-library/] fuzzy search library

Current version is a single instance, slow and serial.   

Next phase willl parallelize to speed thing sup some.
