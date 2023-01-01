This Repository is an attempt to "deep" scrape the FDA CDRH website for keywords at the Summary Document Level

It uses openFDA to get 510(k) numbers, and then the CDRH website and BeautifulSoup to download indivuduals PDFs of the summary documents.

Once downloaded, the PDFs are converted to images and using the tesseract library, converted to serachable text

Text serches are from a keyword list using the fuzzywuzzy fuzzy search library

Current version is a single instance, slow and serial.   

Next phase willl parallelize to speed thing sup some.
