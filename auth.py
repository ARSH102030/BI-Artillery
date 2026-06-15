import msal
from logger import logger

def get_access_token(tenant_id="common"):
    # Using the standard first-party Azure CLI Client ID so you don't need a custom app registration
    client_id = "04b07795-8ddb-461a-bbee-02f9e1bf7b46" 
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    
    # The default Fabric scope allows access to most Fabric and PBI APIs
    scopes = ["https://api.fabric.microsoft.com/.default"]

    app = msal.PublicClientApplication(client_id=client_id, authority=authority)
    
    logger.info("Attempting to authenticate interactively. Please check your browser...")
    result = app.acquire_token_interactive(scopes=scopes, prompt="select_account")

    if "access_token" in result:
        logger.info("Authentication successful.")
        return result["access_token"]
    else:
        logger.error(f"Authentication failed: {result.get('error_description', result.get('error'))}")
        raise Exception("Failed to authenticate.")