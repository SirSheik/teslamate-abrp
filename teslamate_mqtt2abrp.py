## [ IMPORTS ]
import sys
import json #TODO/TODELETE: Needed?
import datetime
import calendar
import os
from time import sleep
import paho.mqtt.client as mqtt
import requests

## [ CONFIGURATION ]
APIKEY = os.environ['API_KEY'] #TODO: ask ABRP/Iternio for an "official" API key
MQTTSERVER = os.environ['MQTT_SERVER']
MQTTUSERNAME = os.environ['MQTT_USERNAME']
MQTTPASSWORD = os.environ['MQTT_PASSWORD']
USERTOKEN = os.environ['USER_TOKEN']
CARNUMBER = os.environ['CAR_NUMBER']
#car model list here curl --location --request GET 'https://api.iternio.com/1/tlm/get_CARMODELs_list'
CARMODEL = os.environ['CAR_MODEL'] #TODO: is there a way to find this automatically from TeslaMate?

## [ VARS ]
state = "" #car state
prev_state = "" #car state previous loop for tracking
data = { #dictionary of values sent to ABRP API
  "utc": 0,
  "soc": 0,
  "power": 0,
  "speed": 0,
  "lat": "",
  "lon": "",
  "elevation": "",
  "is_charging": 0,
  "is_dcfc": 0,
  "is_parked": 0,
  "battery_range": "",
  "ideal_battery_range": "",
  "ext_temp": "",
  "car_model":f"{CARMODEL}",
  "tlm_type": "api",
  "voltage": 0,
  "current": 0,
  "kwh_charged": 0,
  "heading": "",
}

## [ MQTT ]
# Initialize MQTT client and connect
client = mqtt.Client(f"teslamateToABRP-{CARNUMBER}")
if MQTTUSERNAME is not None:
    if MQTTPASSWORD is not None:
        client.username_pw_set(MQTTUSERNAME, MQTTPASSWORD)
    else:
        client.username_pw_set(MQTTUSERNAME)

client.connect(MQTTSERVER)

def on_connect(client, userdata, flags, rc):  # The callback for when the client connects to the broker
    print("Connected with result code {0}".format(str(rc)))  # Print result of connection attempt
    client.subscribe(f"teslamate/cars/{CARNUMBER}/#")

# Process MQTT messages
def on_message(client, userdata, message):
    global data
    global state
    try:
        #extracts message data from the received message
        payload = str(message.payload.decode("utf-8"))

        #updates the received data
        topic_postfix = message.topic.split('/')[-1]

        if topic_postfix == "plugged_in":
            a=1#noop
        elif topic_postfix == "latitude":
            data["lat"] = payload
        elif topic_postfix == "longitude":
            data["lon"] = payload
        elif topic_postfix == "elevation":
            data["elevation"] = payload
        elif topic_postfix == "speed":
            data["speed"] = int(payload)
        elif topic_postfix == "power":
            data["power"] = int(payload)
            if(data["is_charging"]==1 and int(payload)<-22):
                data["is_dcfc"]=1
        elif topic_postfix == "charger_power":
            if(payload!='' and int(payload)!=0):
                data["is_charging"]=1
                if int(payload)>22:
                    data["is_dcfc"]=1
        elif topic_postfix == "heading":
            data["heading"] = payload
        elif topic_postfix == "outside_temp":
            data["ext_temp"] = payload
        elif topic_postfix == "odometer":
            data["odometer"] = payload
        elif topic_postfix == "ideal_battery_range_km":
            data["ideal_battery_range"] = payload
        elif topic_postfix == "est_battery_range_km":
            data["battery_range"] = payload
        elif topic_postfix == "charger_actual_current":
            if(payload!='' and int(payload) > 0):#charging
                data["current"] = payload
            else:
                del data["current"]
        elif topic_postfix == "charger_voltage":
            if(payload!='' and int(payload) > 5):
                data["voltage"] = payload
            else:
                del data["voltage"]
        elif topic_postfix == "shift_state":
            if payload == "P":
                data["is_parked"]="1"
            elif(payload == "D" or payload == "R"):
                data["is_parked"]="0"
        elif topic_postfix == "state":
            state = payload
            if payload=="driving":
                data["is_parked"]=0
                data["is_charging"]=0
                data["is_dcfc"]=0
            elif payload=="charging":
                data["is_parked"]=1
                data["is_charging"]=1
                data["is_dcfc"]=0
            elif payload=="supercharging":
                data["is_parked"]=1
                data["is_charging"]=1
                data["is_dcfc"]=1
            elif(payload=="online" or payload=="suspended" or payload=="asleep"):
                data["is_parked"]=1
                data["is_charging"]=0
                data["is_dcfc"]=0
        elif topic_postfix == "battery_level":
            data["soc"] = payload
        elif topic_postfix == "charge_energy_added":
            data["kwh_charged"] = payload
        elif topic_postfix == "inside_temp":
            a=0#noop
        elif topic_postfix == "since":
            a=0#noop
        else:
            pass
            #print("Unneeded topic:", message.topic, payload)
        return

    except:
        print("unexpected exception while processing message:", sys.exc_info()[0], message.topic, message.payload)

# Starts the MQTT loop processing messages
client.on_message = on_message
client.on_connect = on_connect  # Define callback function for successful connection
client.loop_start()

## [ ABRP ]
# Function to send data to ABRP
def updateABRP():
    global data
    global APIKEY
    global USERTOKEN
    try:
        headers = {"Authorization": "APIKEY "+APIKEY}
        body = {"tlm": data}
        requests.post("https://api.iternio.com/1/tlm/send?token="+USERTOKEN, headers=headers, json=body)
    except:
        print("Unexpected exception while calling ABRP API:", sys.exc_info()[0])
        print(message.topic)
        print(message.payload)

## [ Main ]
# Starts the forever loop updating ABRP
i = -1
while True:
    i+=1
    sleep(5)#refresh rate of min 5 seconds
    #print(state)
    if state != prev_state:
        i = 120
    current_datetime = datetime.datetime.utcnow()
    current_timetuple = current_datetime.utctimetuple()
    data["utc"] = calendar.timegm(current_timetuple)#utc timestamp must be in every message
    if(state == "parked" or state == "online" or state == "suspended" or state=="asleep" or state=="offline"):#if parked update every 10min
        if "kwh_charged" in data:
            del data["kwh_charged"]
        if(i%120==0 or i>120):
            print("parked, updating every 10min")
            print(data)
            updateABRP()
            i = 0
    elif state == "charging":
        if i%6==0:
            print("charging, updating every 30s")
            print(data)
            updateABRP()
    elif state == "driving":
        print("driving, updating every 5s")
        print(data)
        updateABRP()
    else:
        print("unknown state, not updating abrp")
        print(state)
    prev_state = state

client.loop_stop()
