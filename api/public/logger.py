import logging
import os

if not os.path.exists('./logs'):os.makedirs('./logs')

logging.basicConfig(level=logging.INFO,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S',
                filename='./logs/log.txt',
                filemode='a')

log = logging