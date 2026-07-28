# Terraform Configuration for FinSentry Agent Infrastructure

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type        = string
  description = "The GCP Project ID where infrastructure resources will be provisioned."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "The target region for GCP services."
}

variable "agent_service_account_email" {
  type        = string
  description = "The service account email address used by the FinSentry agent runtime."
}

# 1. Provision Secret Manager for secure secrets storage
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"

  replication {
    automatic = true
  }
}

# 2. Grant Access Permissions to Agent Service Account to read Secret
resource "google_secret_manager_secret_iam_member" "agent_secret_access" {
  secret_id = google_secret_manager_secret.gemini_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.agent_service_account_email}"
}

# 3. Provision Cloud Firestore Database for Session persistence
resource "google_firestore_database" "session_db" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_ONLY"

  # Prevent accidental deletion in production
  concurrency_mode = "OPTIMISTIC"
}

# 4. Grant Access Permissions to Agent Service Account for Firestore database operations
resource "google_project_iam_member" "agent_firestore_access" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${var.agent_service_account_email}"
}
