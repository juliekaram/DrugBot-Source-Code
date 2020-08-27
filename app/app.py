import os
import flask
from dotenv import load_dotenv

load_dotenv(verbose=True)

ROOT_PATH = os.environ.get('ROOT_PATH', '/DrugBot/')
# Load any additional configuration parameters via
#  environment variables--`../.env` can be used
#  for sensitive information!

app = flask.Flask(__name__,
  static_url_path=ROOT_PATH + 'static',
)

@app.route(ROOT_PATH + 'static')
def staticfiles(path):
  return flask.send_from_directory('static', path)

@app.route(ROOT_PATH, methods=['GET'])
def index():
    return flask.render_template('index.html')

# Add the rest of your routes....

from slackeventsapi import SlackEventAdapter
from slack import WebClient
import csv
from flask import request, make_response
import requests
import json
import threading
import io
import time

# DRUG INFORMATION/ PARSING

# import drugbank metadata; used for drug name synonym parsing
path = "app/static/drugbank vocabulary.csv"
file = open(path, newline= "")
reader = csv.reader(file)

header = next(reader)
data = [row for row in reader]

def drug_search(drug_name: str):
    '''function searches for drug in drugbank metadata and outputs drugbank id'''
    for row in data:
        for item in row:
            if drug_name.lower() == item.lower():
                return(row[0])

def drug_bank_link(drug_name: str):
    '''given drug name, returns link to drug bank page for drug'''
    DRUGBANK = os.environ.get('drugbank')
    return(DRUGBANK + drug_search(drug_name))

# import L1000FWD metadata; will be used to match drug name to pertid
path2 = "app/static/Drugs_metadata.csv"
file2 = open(path2, newline= "")
reader2 = csv.reader(file2)

header2 = next(reader2)
data2 = [row for row in reader2]

def name_search(drug_name: str):
    '''function searches for drug in drugbank metadata and drug name from drugbank'''
    for row in data:
        for item in row:
            if drug_name.lower() == item.lower():
                return(row[2])

pertid = {}
def pertid_dict(info):
    '''function creates dictionary with drug names as keys and pertids as values'''
    for item in info:
        id = item[0]
        name = item[2]
        pertid[name] = id

# load dictionary pertid dictionary
pertid_dict(data2)

def pertid_match(drug_name):
    '''function matches drug name to pertid'''
    drug = drug_name.lower()
    if (drug in pertid.keys()) == True:
        return pertid[drug]
    elif name_search(drug_name) in pertid.keys():
        return pertid[name_search(drug_name)]
    else:
        return "False"

def L1000link(drug_name):
    '''given drug name, returns link to L1000FWD page for drug'''
    L1000_link = os.environ.get('l1000')
    return(L1000_link + pertid_match(drug_name))

# /DRUG COMMAND OUTPUT: Drug Summary + Links
def drug_summary(drug_name):
    '''function takes in drug name and outputs summary; if drug name not found in drug bank data,
    L1000FWD data will be searched through and outputted'''
    if drug_search(drug_name) == None:
        if (str(drug_name)).lower() in pertid.keys():
            return("*Drug Summary:* " + drug_name + "\n:l1000: *L1000FWD*: " + L1000link(drug_name))
        else:
            return("*Invalid Entry*: Drug Not Found")
    elif pertid_match(drug_name) == "False":
        return("*Drug Summary: " + drug_name + "*\n https://www.drugbank.ca/drugs/" + drug_search(drug_name))
    else:
        return("*Drug Summary: " + drug_name + "*\n https://www.drugbank.ca/unearth/q?utf8=%E2%9C%93&searcher=drugs&query=" + drug_name +
               "\n:l1000: *L1000FWD*: " + L1000link(drug_name))

# ENRICHMENT ANALYSIS
# Library
def library(text):
    '''checks if library is specified in input'''
    if ('[' or ']' in text):
        list = (str(text)).strip('][').split(', ')
        if "_" in list[0]:
            return list
        elif list[0] in drug_library_acronyms.keys():
            return list
        else:
            return False
    else:
        return False

def drug_library_name(text):
    '''outputs library used for graph analysis based on text input'''
    if type(library(text)) == list:
        if library(text)[0] in drug_library_acronyms.keys():
            return drug_library_acronyms[(library(text)[0])]
    elif library(text) == False:
        return 'Geneshot_Predicted_Enrichr'
    else:
        return library(text)[0]

# Drug List
def create_druglist(text):
    '''takes in text and outputs formatted list of drugs that can be analyzed by drugenrichr'''
    if type(library(text)) == list:
        drugs = [drug.lower() for drug in library(text)]
        druglist = (drugs)[1:]
        if len(druglist) == 1:
            if ' ' in druglist[0]:
                return (str(druglist[0])).strip('][').split(' ')
            else:
                return (str(druglist[0])).strip('][').split('\n')
        else:
            return drugs[1:]
    else:
        if type(text) == list:
            return [drug.lower() for drug in text]
        else:
            if (text[0] == "[") and (text[-1] == "]"):
                drugs = text[1:-1]
                drug_list = drugs.split(", ")
                return [drug.lower() for drug in drug_list][1:]
            else:
                if "," in text:
                    drug_list = text.split(", ")
                    return [drug.lower() for drug in drug_list]
                elif " " in text:
                    drug_list = text.split(" ")
                    return [drug.lower() for drug in drug_list]
                else:
                    drug_list = text.split("\n")
                    return [drug.lower() for drug in drug_list]

# DRUGSET INPUT INFORMATION
def drugenrichr(drug_list):
    '''drugenrichr api that takes in user inputted drugset and outputs identifiers for data'''
    ENRICHR_URL = 'http://amp.pharm.mssm.edu/DrugEnrichr/addList'
    drugs_str = '\n'.join(create_druglist(drug_list))
    description = 'Example drug list'
    payload = {
        'list': (None, drugs_str),
        'description': (None, description)
    }

    response = requests.post(ENRICHR_URL, files=payload)
    if not response.ok:
        raise Exception('Error analyzing drug list')

    data = json.loads(response.text)
    return(data)

def drug_enrichment(drug_list):
    '''drugenrichr api that takes in user inputted drugset and outputs enrichment data'''
    ENRICHR_URL = 'http://amp.pharm.mssm.edu/DrugEnrichr/enrich'
    query_string = '?userListId=%s&backgroundType=%s'
    user_list_id = (drugenrichr(drug_list))['userListId']
    drug_set_library = drug_library_name(drug_list)
    response = requests.get(
        ENRICHR_URL + query_string % (user_list_id, drug_set_library)
    )

    if not response.ok:
        raise Exception('Error fetching enrichment results')

    data = json.loads(response.text)
    return(data)

# DRUGSET OUTPUT LINKS + INFORMATION
def drugenrichr_link(drug_list):
    '''outputs links to drugenrichr and information about drugset'''
    if (len(drug_list)) > 10:
        drugs = (', '.join((drug_list)[:10]))
        count = str(len(drug_list))
        rest = str((len(drug_list)) - 10)
        return(":drugenrichr: *DrugEnrichr*: " + "https://amp.pharm.mssm.edu/DrugEnrichr/enrich?dataset=" + drugenrichr(drug_list)['shortId'] +
                "\n:black_small_square:  *Drug Set:* " + drugs + " + " + rest + " more drugs..." +
               "\n:black_small_square:  *Drug Count:* " + count
               )
    else:
        drugs = (', '.join(drug_list))
        count = str(len(drug_list))
        return(":drugenrichr: *DrugEnrichr*: " + "https://amp.pharm.mssm.edu/DrugEnrichr/enrich?dataset=" + drugenrichr(drug_list)['shortId'] +
                "\n:black_small_square:  *Drug Set:* " + drugs +
               "\n:black_small_square:  *Drug Count:* " + count
               )

# ENRICHMENT ANALYSIS: GRAPHS
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import numpy
import uuid
import os

def get_color(x):
    '''colors for graphs based on significance cutoffs; darker colors = more significant'''
    if(x < 0.001):
        return "#8B0000"
    elif((x >= 0.001) and (x <= 0.01)):
        return "#c94c4c"
    elif((x >= 0.01) and (x <= 0.05)):
        return "#F08080"
    elif(x > 0.05):
        return "#b2b2b2"

def text_color(x):
    if(x < 0.01):
        return "#DCDCDC"
    else:
        return "#000000"

def drugenrichr_graph(drug_set):
    '''creates bar graph from drug set data'''
    data = (list((drug_enrichment(drug_set)).values()))[0]
    data.sort(key= lambda x: x[2])
    name = [item[1] for item in data][:10]
    pvalue = [item[2] for item in data][:10]
    convertedpvalues = [numpy.negative(numpy.log10(item)) for item in pvalue]
    labels = [(numpy.around(item, decimals=6)) for item in pvalue]
    colors = [get_color(v) for v in pvalue]
    text_colors = [text_color(v) for v in pvalue]
    title = drug_library_name(drug_set).replace("_", " ")

    plt.rcdefaults()
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.subplots_adjust(left=0.315, right=0.88)

    ax.barh(name, convertedpvalues, align='center', color = colors)
    ax.set_yticks(name)
    ax.set_yticklabels(name)
    ax.invert_yaxis()
    ax.set_xlabel('-log(p-value)', fontsize=14)
    ax.set_title(title, fontsize=20, weight='bold')

    for i, v in enumerate(convertedpvalues):
        plt.text(v - (max(convertedpvalues))/9, i + 0.08, labels[i], color=text_colors[i])

    name = str(uuid.uuid1())

    plt.savefig(name + ".pdf")
    return(name + ".pdf")

# HELPER COMMANDS
def drug_help():
    '''general help function for /drugset command'''
    return(
        "*How to use @DrugBot for enrichment analysis:* \n"
        ":black_small_square: *Slash Command:* Each drug in the input can be separated by a space or comma. (/drugset slashcommand?)\n"
        ":black_small_square: *File Upload:* Alternatively, you can upload the list as a csv file. In this case, you must call @drugbot rather than use /drugset. (/geneset fileupload?)\n"
        ":black_small_square: *Library Specification:* To specify library output, you must call @drugbot followed by your library name. (ie '@drugbot Geneshot_Associated')."
        "DrugBot supports both acronyms and exact DrugEnrichr library names. (/drugset library?)"
    )

def slash_drug_help():
    '''help function that provides information about how to use /drugset command'''
    return(
        "*Example Inputs: Text*\n"
        ":black_small_square: Space Separated: '/drugset gene1 gene2 gene3...' \n"
        ":black_small_square: Comma Separated: '/drugset gene1, gene2, gene3...' \n"
        ":black_small_square: Library Specified: '/drugset [library, gene1, gene2, gene3...]' or '/drugset [library, gene1 gene2 gene3...]'"
    )

def file_drug_help():
    '''help function that provides information about how to upload file data'''
    return(
        "*Example Inputs: Files*\n"
        ":black_small_square: '@drugbot' uploaded_file' or '@drugbot library' uploaded_file\n"
        ":black_small_square: DrugBot currently supports these files...  "
    )

def library_drug_help():
    '''help function that provides information about libraries'''
    return(
        "*Library Acronyms Supported by DrugBot:* \n"
        ":black_small_square: *GSA* = Geneshot_Associated\n"
        ":black_small_square: *GSPE* = Geneshot_Predicted_Enrichr\n"
        ":black_small_square: *DB* = DrugBank_Small-molecule_Target\n"
        ":black_small_square: *L1000D* = L1000FWD_GO_Biological_Processes_Down\n"
        ":black_small_square: *STITCH* = STITCH_Target\n"
        ":black_small_square: *SIDER* = SIDER_Side_Effects\n"
        "For full list of drug-set libraries, visit https://amp.pharm.mssm.edu/DrugEnrichr/#stats"
    )

def help_me():
    '''lists all help functions'''
    return(
        "*Help Commands:* \n"
        ":black_small_square: /drugset ? \n"
        ":black_small_square: /drugset slashcommand? \n"
        ":black_small_square: /drugset fileupload? \n"
        ":black_small_square: /drugset library? \n"
    )

# DRUG LIBRARY ACRONYMS
# can add more...
drug_library_acronyms = {
    "GSA": "Geneshot_Associated",
    "GSPE": "Geneshot_Predicted_Enrichr",
    "DB": "DrugBank_Small-molecule_Target",
    "L1000D": "L1000FWD_GO_Biological_Processes_Down",
    "STITCH": "STITCH_Target-seq_2015",
    "SIDER": "SIDER_Side_Effects"
}

# SLACK FUNCTIONS!
# set up events adapter and client
slack_events_adapter = SlackEventAdapter((os.environ["slack_signing_secret"]), ROOT_PATH + "/slack/events", app)
slack_client = WebClient(os.environ["slack_bot_token"])

# /DRUG COMMAND
@app.route(ROOT_PATH + '/drug', methods=['POST'])
def drug():
    info = request.form

    drug = info['text']
    drugsummary = drug_summary(drug)
    channel = info['channel_id']

    channelMsg = slack_client.chat_postMessage(
        channel= channel,
        text= drugsummary)

    return make_response("", 200)

# /DRUGSET COMMAND
@app.route(ROOT_PATH + '/drugset', methods=['POST'])
def drugset():
    info = request.form
    channel = info['channel_id']

    if info['text'] == "?":
        channelMsg = slack_client.chat_postMessage(
        channel= channel,
        text= drug_help())
        return make_response("", 200)

    elif info['text'] == "slashcommand?":
        channelMsg = slack_client.chat_postMessage(
        channel= channel,
        text= slash_drug_help())
        return make_response("", 200)

    elif info['text'] == "fileupload?":
        channelMsg = slack_client.chat_postMessage(
        channel= channel,
        text= slash_drug_help())
        return make_response("", 200)

    elif info['text'] == "help?":
        channelMsg = slack_client.chat_postMessage(
        channel= channel,
        text= help_me())
        return make_response("", 200)

    else:
        x = threading.Thread(
                target=some_processing2,
                args=[info]
            )
        x.start()

        channelMsg = slack_client.chat_postMessage(
            channel= channel,
            text= ":hourglass_flowing_sand: Processing input: */drugset " + info['text'] + "* \n" +
                                                                                    ":hourglass: Please wait a moment...")
        return make_response("", 200)

def some_processing2(info):
    drugset = create_druglist(info['text'])
    enrichment_analysis = drugenrichr_link(drugset)
    channel = info['channel_id']
    graph = drugenrichr_graph(info['text'])

    filepath = graph

    time.sleep(10)

    slack_client.chat_postMessage(
                channel= channel,
                text= enrichment_analysis)

    with open(filepath, 'rb') as f:
            slack_client.files_upload(
                channels = channel,
                filename = drug_library_name(info['text']),
                file = io.BytesIO(f.read())
            )
            os.remove(filepath)
            return make_response("", 200)

# FILES
def get_file_data(id):
    '''load data from user uploaded files'''
    path3 = id
    file3 = open(path3, newline= "")
    reader3 = csv.reader(file3)

    header = next(reader3)
    data3 = [row for row in reader3]
    return([item for sublist in data3 for item in sublist])

def drug_enrichment2(drug_list: list, library: str):
    '''drugenrichr api that takes in user inputted drugset and library and outputs enrichment data'''
    ENRICHR_URL = 'http://amp.pharm.mssm.edu/DrugEnrichr/enrich'
    query_string = '?userListId=%s&backgroundType=%s'
    user_list_id = (drugenrichr(drug_list))['userListId']
    drug_set_library = library
    response = requests.get(
        ENRICHR_URL + query_string % (user_list_id, drug_set_library)
    )

    if not response.ok:
        raise Exception('Error fetching enrichment results')

    data = json.loads(response.text)
    return(data)

def drugenrichr_graph2(drug_set, library):
    '''creates bar graph from file uploaded drug set data'''
    data = (list((drug_enrichment2(drug_set, library)).values()))[0]
    data.sort(key= lambda x: x[2])
    name = [item[1] for item in data][:10]
    pvalue = [item[2] for item in data][:10]
    convertedpvalues = [numpy.negative(numpy.log10(item)) for item in pvalue]
    labels = [(numpy.around(item, decimals=6)) for item in pvalue]
    colors = [get_color(v) for v in pvalue]
    text_colors = [text_color(v) for v in pvalue]
    title = library.replace("_", " ")

    plt.rcdefaults()
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.subplots_adjust(left=0.315, right=0.88)

    ax.barh(name, convertedpvalues, align='center', color = colors)
    ax.set_yticks(name)
    ax.set_yticklabels(name)
    ax.invert_yaxis()
    ax.set_xlabel('-log(p-value)', fontsize=14)
    ax.set_title(title, fontsize=20, weight='bold')

    for i, v in enumerate(convertedpvalues):
        plt.text(v - (max(convertedpvalues))/9, i + 0.08, labels[i], color=text_colors[i])

    name = str(uuid.uuid1())

    plt.savefig(name + ".pdf")
    return(name + ".pdf")

# ANALYSIS FOR FILES
@slack_events_adapter.on("message")
def handle_message(event_data):
    message = event_data["event"]
    if "<@U015VH8VD8F>" in message.get('text') and 'files' in message:
        file = (message.get('files'))[0]
        url = file['url_private']
        id = file['id']
        channel = message["channel"]
        token = (os.environ["slack_bot_token"])
        library = drug_library_name2(message)

        r = requests.get(url, headers={'Authorization': 'Bearer %s' % token})
        r.raise_for_status()
        file_data = r.content

        with open(id , 'w+b') as f:
            f.write(bytearray(file_data))
            print("Saved " + id + " in current folder")

        if type(library) == str:
            xx = threading.Thread(
                target=some_processing3,
                args=[message]
            )
            xx.start()

            drugs = get_file_data(id)

            channelMsg = slack_client.chat_postMessage(
                channel= channel,
                text= ":hourglass_flowing_sand: Processing input: *" + message['text'] + " <file>* \n" +
                                                                                    ":hourglass: Please wait a moment...")
            return make_response("", 200)

def drug_library_name2(message):
    library = (str(message['text']))[15:]
    if library in drug_library_acronyms.keys():
        return drug_library_acronyms[library]
    elif library == "":
        return 'Geneshot_Predicted_Enrichr'
    else:
        return library

def some_processing3(message):
    file = (message.get('files'))[0]
    id = file['id']
    drugs = get_file_data(id)
    enrichment_analysis = drugenrichr_link(drugs)
    channel = message["channel"]
    library2 = drug_library_name2(message)
    graph = drugenrichr_graph2(drugs, library2)

    time.sleep(10)

    slack_client.chat_postMessage(
        channel= channel,
        text= enrichment_analysis)

    with open(graph, 'rb') as f:
            slack_client.files_upload(
                channels = channel,
                filename = library2,
                file = io.BytesIO(f.read())
            )
            os.remove(graph)
            os.remove(id)
            return make_response("", 200)

################################################################################
