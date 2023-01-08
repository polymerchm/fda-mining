import os
import argparse



fileCount = 0
file_list = []
for root, dirs, files in os.walk('pdf'):

    if len(dirs) == 0 or root == 'pdf':
        continue
    else:
        file_list.append((root, len(dirs)))
        fileCount += len(dirs)
        
        
file_list.sort(key=lambda x: x[0])
for dir,count in file_list:
    print(f'{dir}     {count}')
print(fileCount)
        
    
