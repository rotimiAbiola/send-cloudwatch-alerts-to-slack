import urllib3
import json
import boto3
from botocore.exceptions import ClientError

def get_secret():
    secret_name = "prod/slack/webhook-url"
    region_name = "eu-west-2"

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        # Parse the JSON string from SecretString
        secret_dict = json.loads(get_secret_value_response['SecretString'])
        return secret_dict['webhook_url']
    except ClientError as e:
        print(f"Error getting secret: {str(e)}")
        raise e
    except KeyError as e:
        print("Error: Secret value doesn't contain 'webhook_url' key")
        raise e
    except json.JSONDecodeError as e:
        print("Error: Secret value is not valid JSON")
        raise e

def get_alarm_attributes(sns_message):
    alarm = dict()

    alarm['name'] = sns_message['AlarmName']
    alarm['description'] = sns_message['AlarmDescription']
    alarm['reason'] = sns_message['NewStateReason']
    alarm['region'] = sns_message['Region']
    alarm['state'] = sns_message['NewStateValue']
    alarm['previous_state'] = sns_message['OldStateValue']

    # Safely get instance_id if it exists
    try:
        if 'Dimensions' in sns_message['Trigger'] and sns_message['Trigger']['Dimensions']:
            alarm['instance_id'] = sns_message['Trigger']['Dimensions'][0]['value']
    except (KeyError, IndexError):
        alarm['instance_id'] = 'N/A'

    return alarm

def register_alarm(alarm):
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":warning: " + alarm['name'] + " alarm was registered"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_" + alarm['description'] + "_"
                },
                "block_id": "text1"
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Region: *" + alarm['region'] + "*"
                    }
                ]
            }
        ]
    }

def activate_alarm(alarm):
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":red_circle: Alarm: " + alarm['name'],
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_" + alarm['reason'] + "_"
                },
                "block_id": "text1"
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Region: *" + alarm['region'] + "*"
                    }
                ]
            }
        ]
    }

def resolve_alarm(alarm):
    return {
        "type": "home",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": ":large_green_circle: Alarm: " + alarm['name'] + " was resolved",
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "_" + alarm['reason'] + "_"
                },
                "block_id": "text1"
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Region: *" + alarm['region'] + "*"
                    }
                ]
            }
        ]
    }

def lambda_handler(event, context):
    try:
        slack_url = get_secret()
        http = urllib3.PoolManager()
        
        sns_message = json.loads(event["Records"][0]["Sns"]["Message"])
        alarm = get_alarm_attributes(sns_message)
        
        print(f"State transition: {alarm['previous_state']} -> {alarm['state']}")

        msg = None
        # Handle all possible state transitions
        if alarm['state'] == 'ALARM':
            msg = activate_alarm(alarm)
        elif alarm['state'] == 'OK':
            if alarm['previous_state'] == 'ALARM':
                msg = resolve_alarm(alarm)
            else:
                msg = register_alarm(alarm)
        else:
            print(f"Unhandled state transition: {alarm['previous_state']} -> {alarm['state']}")
            return {
                'statusCode': 200,
                'body': 'State transition logged'
            }

        if msg:
            encoded_msg = json.dumps(msg).encode("utf-8")
            resp = http.request("POST", slack_url, body=encoded_msg)
            
            response_data = {
                "message": msg,
                "status_code": resp.status,
                "response": resp.data.decode('utf-8')
            }
            print(response_data)
            
            return {
                'statusCode': resp.status,
                'body': json.dumps(response_data)
            }
            
    except Exception as e:
        print(f"Error in lambda execution: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }