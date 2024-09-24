"enable all unclaimed gpus in specified group"

import argparse

from lufah.logger import logger


async def do_enable_all_gpus(args: argparse.Namespace):
    "Enable all unclaimed gpus in specified group."
    client = args.client
    await client.connect()
    if client.version < (8, 3, 17):
        raise Exception("Error: enable-all-gpus requires client 8.3.17+")
    if client.group is None or client.group not in client.groups:
        raise Exception("Error: an existing group must be specified for enable-all-gpus")
    all_gpus = client.data.get("info", {}).get("gpus", {})
    # get set of all_supported gpu ids, info.gpus id with "supported" True
    all_supported = set()
    for gpuid in all_gpus.keys():
        if all_gpus.get(gpuid, {}).get("supported") is True:
            all_supported.add(gpuid)
    if len(all_supported) == 0:
        logger.warning("no supported gpus found")
        return
    # get set of already_enabled gpus across all groups
    already_enabled = set()
    groups_dict = client.data.get("groups", {})
    for group in client.groups:
        gconfgpus = groups_dict.get(group, {}).get("config", {}).get("gpus", {})
        for gpuid in gconfgpus.keys():
            if gconfgpus.get(gpuid, {}).get("enabled") is True:
                already_enabled.add(gpuid)

    to_enable = all_supported - already_enabled
    logger.debug("all_supported: %s", repr(all_supported))
    logger.debug("already_enabled: %s", repr(already_enabled))
    logger.info("to_enable: %s", repr(to_enable))
    if len(to_enable) == 0:
        logger.warning("no gpus to enable")
        return
    # create group config with to_enable gpus, {gpuid = {enabled = True}}
    # start with existing gpus, so we don't disable any in target group
    groupconf = client.data.get("groups", {}).get(client.group, {}).get("config", {})
    target_group_conf_gpus = groupconf.get("gpus", {}).copy()
    for gpuid in to_enable:
        target_group_conf_gpus[gpuid] = {"enabled": True}
    # create config dict {"groups" = {groupname = {},...}}
    # need empty conf for each existing group
    groupsconf = {}
    for g in client.groups:
        groupsconf[g] = {}
    groupsconf[client.group] = {"gpus": target_group_conf_gpus}
    conf = {"groups": groupsconf}
    # send config
    await client.send({"cmd": "config", "config": conf})
