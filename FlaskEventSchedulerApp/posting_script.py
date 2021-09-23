import pandas as pd
import requests
import time



print('loading Excel File!')
df = pd.read_excel('slipstream_event_schedule.xlsx', engine='openpyxl', index_col='Time Block',parse_dates=True)
post_this_json = df.to_json(orient="index")
print('extracting data from the Excel file success!')



print('posting data to API now!')
r = requests.post('http://10.200.200.224:5000/update/data', json=post_this_json)
print(r.text)



print('waiting 30 seconds to check API payload signal....')
time.sleep(30)



r = requests.get('http://10.200.200.224:5000/payload/current')
print('Current Payload is: ',r.text)

time.sleep(5)




