import os
from google.cloud import secretmanager
from google.api_core.exceptions import GoogleAPIError

# Secure Secret Management
def get_secret(secret_id: str, default_env_var: str = None) -> str:
    """Retrieves a secret from Google Cloud Secret Manager.
    
    If the Secret Manager retrieval fails (e.g. due to missing GCP credentials or permissions),
    it falls back to checking the local environment variables.
    
    Args:
        secret_id: The secret identifier in Google Secret Manager.
        default_env_var: The name of the backup environment variable to check.
        
    Returns:
        The secret value as a string.
        
    Raises:
        RuntimeError: If the secret cannot be found in Secret Manager or environment variables.
    """
    gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    
    if gcp_project:
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{gcp_project}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8").strip()
        except GoogleAPIError as e:
            # Guided recovery warning
            print(f"[WARNING] Failed to fetch secret '{secret_id}' from GCP Secret Manager: {e}. "
                  f"Attempting fallback to environment variable.")
        except Exception as e:
            print(f"[WARNING] Unexpected error accessing Secret Manager: {e}. Falling back to env.")

    # Fallback to local environment variable
    fallback_var = default_env_var or secret_id.upper()
    val = os.getenv(fallback_var)
    if val:
        return val
        
    # Raise custom error with explicit instructions
    raise RuntimeError(
        f"Missing secret '{secret_id}' / Environment Variable '{fallback_var}'. "
        "RECOVERY ACTION REQUIRED: Please either: \n"
        "1. Create the secret in Google Cloud Secret Manager under the ID and set GOOGLE_CLOUD_PROJECT.\n"
        f"2. Set the environment variable '{fallback_var}' locally using: export {fallback_var}=<your_key>."
    )

def get_gemini_api_key() -> str:
    """Gets the Gemini API key securely."""
    return get_secret(secret_id="gemini-api-key", default_env_var="GEMINI_API_KEY")
