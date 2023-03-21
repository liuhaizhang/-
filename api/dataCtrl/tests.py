from django.test import TestCase

# Create your tests here.
import datetime
# Create your tests here.

da = (datetime.datetime.now()+datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
print(da)
