import json
import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client("ec2")
TAG_FILTER = {"Name": "tag:AutoSchedule", "Values": ["office-hours"]}


def lambda_handler(event, context):
    action = event.get("action")

    if action == "start":
        required_state = "stopped"
        change_state = ec2.start_instances
        response_key = "StartingInstances"
    elif action == "stop":
        required_state = "running"
        change_state = ec2.stop_instances
        response_key = "StoppingInstances"
    else:
        raise ValueError("action must be 'start' or 'stop'")

    counts = {"accepted": 0, "skipped": 0, "failed": 0}
    paginator = ec2.get_paginator("describe_instances")

    for page in paginator.paginate(Filters=[TAG_FILTER]):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                current_state = instance["State"]["Name"]
                details = {
                    "action": action,
                    "instance_id": instance_id,
                    "observed_state": current_state,
                }

                if current_state != required_state:
                    counts["skipped"] += 1
                    logger.info(json.dumps({**details, "result": "skipped"}))
                    continue

                try:
                    response = change_state(InstanceIds=[instance_id])
                except ClientError as error:
                    counts["failed"] += 1
                    logger.error(json.dumps({
                        **details,
                        "result": "failed",
                        "error_code": error.response["Error"]["Code"],
                        "error_message": error.response["Error"]["Message"],
                    }))
                    continue

                new_state = response[response_key][0]["CurrentState"]["Name"]
                counts["accepted"] += 1
                logger.info(json.dumps({
                    **details,
                    "result": "accepted",
                    "reported_state": new_state,
                }))

    logger.info(json.dumps({"action": action, **counts}))

    if counts["failed"]:
        raise RuntimeError(f"{counts['failed']} EC2 {action} request(s) failed")

    return {"action": action, **counts}