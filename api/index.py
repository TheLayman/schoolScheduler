import json
def handler(event, context):
    try:
        # Parse incoming request (assume JSON payload)
        body = json.loads(event.get("body", "{}"))
        
        # Process config data
        config_data = body.get("config", {})

        # Example transformation (modify as needed)
        response_data = {"status": "success", "message": "Config processed", "config": config_data}

        return {
            "statusCode": 200,
            "body": json.dumps(response_data),
            "headers": {"Content-Type": "application/json"}
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
            "headers": {"Content-Type": "application/json"}
        }