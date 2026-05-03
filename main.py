import gettoken
import getapi
import postapi
import settingsmanager
import os
import re
import requests
import threading
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from src.configuration.configuration import Configuration

# Define console colors for readability
class ConsoleColor:
    OKBLUE = "\033[34m"
    OKCYAN = "\033[36m"
    OKGREEN = "\033[32m"
    MAGENTA = "\033[35m"
    WARNING = "\033[33m"
    FAIL = "\033[31m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"

# Configure logging — write to /data so the location is predictable, with rotation.
LOG_PATH = "/data/solar_script.log"
_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
try:
    os.chmod(LOG_PATH, 0o600)
except OSError:
    pass

# Get current date & time
VarCurrentDate = datetime.now()

# Load settings
try:
    json_settings = Configuration()
    api_server = json_settings['API_Server']
except Exception as e:
    logging.exception("Failed to load settings")
    print(ConsoleColor.FAIL + "Error loading settings.json. Ensure the file exists and is valid JSON." + ConsoleColor.ENDC)
    exit()

# Retrieve inverter serials and validate format
SERIAL_PATTERN = re.compile(r'^[A-Za-z0-9]+$')
_raw_serials = str(json_settings['sunsynk_serial']).split(";")
inverterserials = []
for _s in _raw_serials:
    _s = _s.strip()
    if not _s:
        continue
    if not SERIAL_PATTERN.match(_s):
        print(ConsoleColor.FAIL + f"Skipping invalid inverter serial: {_s!r} (must be alphanumeric)" + ConsoleColor.ENDC)
        logging.warning("Skipping invalid inverter serial: %r", _s)
        continue
    inverterserials.append(_s)

# Function to safely fetch data using threading

def fetch_data(api_function, BearerToken, serialitem, description):
    try:
        print(f"{ConsoleColor.WARNING}Fetching {description}...{ConsoleColor.ENDC}")
        api_function(BearerToken, str(serialitem))
    except Exception as e:
        logging.exception("Error fetching %s", description)
        print(ConsoleColor.FAIL + f"Error fetching {description}: {e}" + ConsoleColor.ENDC)




#Start the Loop
print("------------------------------------------------------------------------------")
print("-- " + ConsoleColor.MAGENTA + f"Running Script SolarSynkV3" + ConsoleColor.ENDC)
print("-- " + "Using API Endpoint: " + ConsoleColor.MAGENTA + json_settings['API_Server'] + ConsoleColor.ENDC )
print("-- https://github.com/martinville/solarsynkv3")
print("------------------------------------------------------------------------------")   

# Get Bearer Token
BearerToken=""
try:
    BearerToken = gettoken.gettoken()
    if not BearerToken:
        print("Failed to retrieve Bearer Token. Check credentials or server status.")
except Exception as e:
    logging.exception("Token retrieval error")
    print(ConsoleColor.FAIL + "Error retrieving Bearer Token." + ConsoleColor.ENDC)
    exit()

# Iterate through all inverters (Only if bearer exist)
if BearerToken:       
    for serialitem in inverterserials:
        
        print(ConsoleColor.OKCYAN + f"Getting {serialitem} @ {VarCurrentDate}" + ConsoleColor.ENDC)
        
        print("Script refresh rate set to: " + ConsoleColor.OKCYAN + str(json_settings['Refresh_rate']) + ConsoleColor.ENDC + " milliseconds")


        print("Cleaning cache...")
        settings_file = "settings.json"
        if os.path.exists(settings_file):
            os.remove(settings_file)
            print("Old settings.json file removed.")

        # Test API connection
        print(ConsoleColor.WARNING + "Testing HA API" + ConsoleColor.ENDC)
        varContest = postapi.ConnectionTest("TEST", "A", "current", "connection_test", "connection_test_current", "100")

        if varContest == "Connection Success":
            print(varContest)

            # Define API calls
            api_calls = [
                (getapi.GetInverterInfo, "Inverter Information"),
                (getapi.GetPvData, "PV Data"),
                (getapi.GetGridData, "Grid Data"),
                (getapi.GetBatteryData, "Battery Data"),
                (getapi.GetLoadData, "Load Data"),
                (getapi.GetOutputData, "Output Data"),
                (getapi.GetDCACTemp, "DC & AC Temperature Data"),
                (getapi.GetInverterSettingsData, "Inverter Settings")
            ]

            # Start threaded API calls
            threads = []
            for api_function, description in api_calls:
                thread = threading.Thread(target=fetch_data, args=(api_function, BearerToken, serialitem, description))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            print(ConsoleColor.OKGREEN + "All API calls completed successfully!" + ConsoleColor.ENDC)

            print("Checking if settings can be processed and flushed...")

            # BOF CHECK SETTINGS ENTITY's EXISTENCE
            # SETUP VARS
            SUPERVISOR_URL = os.getenv("SUPERVISOR", "http://supervisor")
            SUPERVISOR_TOKEN = os.getenv("SUPERVISOR_TOKEN")
            url = f"{SUPERVISOR_URL}/core/api/states/input_text.solarsynkv3_{serialitem}_settings"
            print(ConsoleColor.MAGENTA + "URL --> " + url + ConsoleColor.ENDC)
            
            headers = {
                "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
                "Content-Type": "application/json",
            }
            
            # Connect and get settings entity response details
            try:
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    print(ConsoleColor.OKGREEN + f"URL exists (Status code: {response.status_code}) Settings may be processed and flushed." + ConsoleColor.ENDC)
                    SettingsExist = True
                else:
                    print(ConsoleColor.FAIL + f"Error: Unable to connect to Home Assistant Settings via the API HTTP Error: {response.status_code}. Settings will not be processed or applied. Please create a text entity manually named: [solarsynkv3_{serialitem}_settings]" + ConsoleColor.ENDC)
                    SettingsExist = False
            
            except requests.RequestException as e:
                print(f"Error connecting: {e}")
                SettingsExist = False
            # EOF CHECK SETTINGS ENTITY's EXISTENCE
     



            
            if SettingsExist==True:
                # Download and process inverter settings
                settingsmanager.DownloadProviderSettings(BearerToken, str(serialitem))
                settingsmanager.GetNewSettingsFromHAEntity(BearerToken, str(serialitem))                
                # Clear old settings to prevent re-sending
                settingsmanager.ResetSettingsEntity(serialitem)

        else:
            print(ConsoleColor.FAIL + varContest + ConsoleColor.ENDC)
            print(ConsoleColor.MAGENTA + "Ensure correct IP, port, and Home Assistant accessibility." + ConsoleColor.ENDC)

        # Script completion time
        VarCurrentDate = datetime.now()
        print(f"Script completion time: {ConsoleColor.OKBLUE} {VarCurrentDate} {ConsoleColor.ENDC}") 


print(ConsoleColor.OKBLUE + "Script execution completed." + ConsoleColor.ENDC)
