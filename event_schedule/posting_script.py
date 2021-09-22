import pandas as pd
import requests
import time


df = pd.read_excel('slipstream_event_schedule.xlsx', engine='openpyxl', index_col='Time Block',parse_dates=True)
post_this_json = df.to_json(orient="index")


r = requests.post('http://10.200.200.223:5000/update/data', json=post_this_json)
print(r.text)

time.sleep(5)

r = requests.get('http://10.200.200.223:5000/payload/current')
print('Current Payload is: ',r.text)

time.sleep(5)




