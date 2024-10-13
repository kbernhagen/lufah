"get or set config values"

import argparse
import json

from lufah.const import (
    DEPRECATED_CONFIG_KEYS,
    GLOBAL_CONFIG_KEYS,
    GROUP_CONFIG_KEYS,
    VALID_CONFIG_SET_KEYS,
)
from lufah.logger import logger
from lufah.util import munged_group_name


async def do_config(args: argparse.Namespace):
    """
    Get or set config values.

    Other than for account settings (user, team, passkey, cause),
    a group must be specified if there is more than one group.
    Example:
      lufah -a / config cpus 0
    """
    client = args.client
    await client.connect()
    key = args.key
    value = args.value
    ver = client.version
    # Note: account can be out-of-date, but does become "" when unlinked
    have_acct = 0 < len(client.data.get("info", {}).get("account", ""))

    # FIXME: potential race if groups changes before we write
    # think currently client deletes groups not in group config command
    groups = client.groups  # [] on 8.2; 8.1 may have peer groups
    # we don't care about 8.1 peer groups because everything is in main config
    # just need to be mindful of possible config.available_cpus

    if (8, 3) <= ver:
        try:
            group = munged_group_name(client.group, client.data)
        except Exception as e:
            raise Exception(f"FahClient('{client.name}'):{e}") from e
    else:
        group = client.group

    # don't require group if there is only one (the default group "")
    if group is None and len(groups) == 1:
        group = groups[0]

    # v8.3 splits config between global(account) and group

    key0 = key  # might exist in 8.1
    key = key.replace("-", "_")  # convert cli keys to actual

    if value is None:
        # print value for key
        if (8, 3) <= ver and key in GROUP_CONFIG_KEYS:
            if group is None:
                raise Exception(
                    f'Error: cannot get "{key0}" on unspecified group.'
                    f" There are {len(groups)} groups."
                )
            # client.data.groups.{group}.config
            conf = client.data.get("groups", {}).get(group, {}).get("config", {})
            print(json.dumps(conf.get(key)))
        else:
            # try getting key, no matter what it is
            conf = client.data.get("config", {})
            print(json.dumps(conf.get(key, conf.get(key0))))
        return

    if "cpus" == key:
        maxcpus0 = client.data.get("info", {}).get("cpus", 0)
        # available_cpus in fah v8.1.19 only
        maxcpus = client.data.get("config", {}).get("available_cpus", maxcpus0)
        if value > maxcpus:
            raise Exception(f"Error: cpus is greater than available cpus {maxcpus}")
        # FIXME: cpus are in groups on fah 8.3; need to sum cpus across groups
        # available_cpus = maxcpus - total_group_cpus
        # if value > (available_cpus - current_group_cpus)
        # this is simpler if only have one group (the default group)
        # no need to calc available_cpus if new value is 0
        # NOTE: client will not limit cpus value sent for us

    if (8, 3) <= ver:
        if key in DEPRECATED_CONFIG_KEYS:
            raise Exception(f'Error: key "{key0}" is deprecated in fah 8.3')
        if key not in VALID_CONFIG_SET_KEYS:
            raise Exception(f'Error: setting "{key0}" is not supported in fah 8.3')
        if have_acct and key in GLOBAL_CONFIG_KEYS:
            logger.warning("Machine is linked to an account")
            logger.warning('"%s" "%s" may be overwritten by account', key0, value)

    # TODO: don't send if value == current_value
    conf = {key: value}
    msg = {"cmd": "config", "config": conf}
    if (8, 3) <= ver and key in GROUP_CONFIG_KEYS:
        if group is None:
            raise Exception(
                f'Error: cannot set "{key0}" on unspecified group. There are {len(groups)} groups.'
            )
        # create appropriate 8.3 config.groups dict with all current groups
        groupsconf = {}
        for g in groups:
            groupsconf[g] = {}
        groupsconf[group] = conf
        msg["config"] = {"groups": groupsconf}
    await client.send(msg)
