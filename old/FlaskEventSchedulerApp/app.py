from flask import Flask, request, jsonify
from flask.helpers import make_response
from functools import wraps
from flask_caching import Cache
import numpy as np
import pandas as pd
import datetime
from sqlalchemy import create_engine
from time import strftime 
import time
import pytz
import sqlite3





tz = pytz.timezone('America/Chicago')

cache = Cache()
app = Flask(__name__)
cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})






@cache.cached(timeout=60, key_prefix='get_state_from_df')
def get_state_from_df():
    try:
        con = sqlite3.connect('payload_storage.db')
        df = pd.read_sql("SELECT * from payload_data", con)
        df.rename(columns={'index':'Time Block'}, inplace=True)
        df.set_index('Time Block')
        df['Time Block'] = pd.to_datetime(df['Time Block']).dt.round(freq='T')
        utc_time = datetime.datetime.utcnow()
        utc_time = utc_time.replace(tzinfo=pytz.UTC)   
        corrected_time = utc_time.astimezone(tz) 
        current_block = corrected_time.replace(minute = (corrected_time.minute - corrected_time.minute % 15), second=0, microsecond=0)
        current_block_no_tz = current_block.replace(tzinfo=None)

        # brute force through excel file to find a matching date
        for row in df.iterrows():
            if row[1][0].replace(second=0, microsecond=0) == current_block_no_tz:
                date = row[1][0].replace(second=0, microsecond=0)
                info = f'timeblock is {date}'
                response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':row[1][1]}
                print(response_obj)   
                return jsonify(response_obj), 200 

        info = "timeblock not found"
        response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
        print(response_obj)   
        return jsonify(response_obj), 200   

    except Exception as error:
        err = f"Internal Server Error - {error}"
        response_obj = {'status':'fail','info':err,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
        print(response_obj)   
        return jsonify(response_obj), 500   


@cache.cached(timeout=300, key_prefix='get_hourly_from_df')
def get_hourly_from_df():
    try:

        hours = 4
        con = sqlite3.connect('payload_storage.db')
        df = pd.read_sql("SELECT * from payload_data", con)
        df.rename(columns={'index':'Time Block'}, inplace=True)
        df.set_index('Time Block')
        df['Time Block'] = pd.to_datetime(df['Time Block']).dt.round(freq='T')
        utc_time = datetime.datetime.utcnow()
        utc_time = utc_time.replace(tzinfo=pytz.UTC)   
        corrected_time = utc_time.astimezone(tz) 
        current_block = corrected_time.replace(minute = (corrected_time.minute - corrected_time.minute % 15), second=0, microsecond=0)
        current_block_no_tz = current_block.replace(tzinfo=None)

        # brute force through excel file to find a matching date
        for row in df.iterrows():
            if row[1][0].replace(second=0, microsecond=0) == current_block_no_tz:
                date = row[1][0].replace(second=0, microsecond=0)
                info = f'timeblock is {date}'
                
                slice_start = row[0]
                slice_end = row[0] + hours
                sliced_df = df[slice_start:slice_end]
                sliced_data = sliced_df.to_json(orient='records')
                
                response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':row[1][1],'hourly':sliced_data}
                print(response_obj)    
                return jsonify(response_obj), 200 

        info = "Internal Server Error - unable to compile future results"
        response_obj = {'status':'fail','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz)}
        print(response_obj)   
        return jsonify(response_obj), 500   

    except Exception as error:
        err = f"Internal Server Error - {error}"
        response_obj = {'status':'fail','info':err,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
        print(response_obj)   
        return jsonify(response_obj), 500   




@app.route('/payload/current', methods=['GET'])
def event_state_current():
    return get_state_from_df()    



@app.route('/payload/hourly,', methods=['GET'])
def event_state_hourly():
    return get_hourly_from_df()    



@app.route('/update/data', methods=['POST'])
def json_payloader():


    try:
        r = request.json
        df = pd.read_json(r).T


        engine = create_engine('sqlite:///payload_storage.db', echo=True)
        sqlite_connection = engine.connect()
        sqlite_table = "payload_data"
        df.to_sql(sqlite_table, sqlite_connection, if_exists='replace')
        sqlite_connection.close()

        response_obj = {'status':'success','info':'parsed and saved success','timezone_config':str(tz)}
        print(response_obj)   
        return jsonify(response_obj), 200     

    except Exception as error:
        err = f"Internal Server Error - {error}"
        response_obj = {'status':'fail','info':err,'timezone_config':str(tz)}
        print(response_obj)   
        return jsonify(response_obj), 500   



if __name__ == '__main__':
    app.run(debug=False,port=5000,host='0.0.0.0')
