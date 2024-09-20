"""constants"""

COMMAND_FOLD = "fold"
COMMAND_FINISH = "finish"
COMMAND_PAUSE = "pause"

# fah 8.3 config keys
# valid global/group keys are in json files:
# https://github.com/FoldingAtHome/fah-client-bastet/tree/master/src/resources
# note that these are the actual keys with underscore

# keys to settings possibly owned by account (if logged in)
# Joseph says it's safe to change these while logged in
# it is possible for a machine to differ from account
# web control will only show the account values when logged in
GLOBAL_CONFIG_KEYS = ["user", "team", "passkey", "cause"]

# keys to settings in groups under v8.3; in main config before 8.3
# cuda added for 8.4
GROUP_CONFIG_KEYS = [
    "on_idle",
    "beta",
    "key",
    "cpus",
    "on_battery",
    "keep_awake",
    "cuda",
]

# peers is v8.1.x only, but possibly remains as cruft
# gpus, paused, finish in main config before 8.3
READ_ONLY_GLOBAL_KEYS = ["peers", "gpus", "paused", "finish"]
# should never be changed externally for any fah version
READ_ONLY_GROUP_KEYS = ["gpus", "paused", "finish"]

READ_ONLY_CONFIG_KEYS = READ_ONLY_GLOBAL_KEYS + READ_ONLY_GROUP_KEYS
VALID_CONFIG_SET_KEYS = GLOBAL_CONFIG_KEYS + GROUP_CONFIG_KEYS
VALID_CONFIG_GET_KEYS = VALID_CONFIG_SET_KEYS + READ_ONLY_CONFIG_KEYS

# removed in 8.3
DEPRECATED_CONFIG_KEYS = ["fold_anon", "peers", "checkpoint", "priority"]

KNOWN_CAUSES = [
    "any",
    "alzheimers",
    "cancer",
    "huntingtons",
    "parkinsons",
    "influenza",
    "diabetes",
    "covid-19",
]

# From Web Control src/unit.js
# some of these are synthetic (not actual unit.state)
# client can return pause_reason strings longer than 16 chars
STATUS_STRINGS = {
    "ASSIGN": "Assigning",
    "DOWNLOAD": "Downloading",
    "CORE": "Core",
    "RUN": "Running",
    "FINISH": "Finishing",
    "UPLOAD": "Uploading",
    "CLEAN": "Ended",
    "WAIT": "Waiting",
    "PAUSE": "Paused",
    "DUMP": "Dumping",
    "DUMPED": "Dumped",
    "EXPIRED": "Expired",
    "ABORTED": "Aborted",
    "MISSING": "Missing Data",
    "RETRIES": "Max Retries",
    "FAILED": "Failed",
    "REJECTED": "Rejected",
    "CREDITED": "Credited",
}

WAIT_STATUS_STRINGS = {
    "ASSIGN": "Assign Wait",
    "DOWNLOAD": "Download Wait",
    "CORE": "Core Wait",
    "RUN": "Run Wait",
    "UPLOAD": "Upload Wait",
    "DUMP": "Dump Wait",
}
