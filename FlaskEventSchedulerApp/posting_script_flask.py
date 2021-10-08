import pandas as pd
import requests
import time


linux_vm = 'http://10.200.200.223:5000/update/data'


print('loading Excel File!')
df = pd.read_excel('slipstream_event_schedule.xlsx', engine='openpyxl', index_col='Time Block',parse_dates=True)
post_this_json = df.to_json(orient="index")
print('extracting data from the Excel file success!')


print(f'posting data to API now @ {linux_vm}!')
r = requests.post(linux_vm, json=post_this_json)
print(r.text)


print('check in web broswer http://10.200.200.223:5000/payload/current')

time.sleep(30)



