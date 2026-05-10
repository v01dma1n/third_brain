# Personal Facts — Base
#
# This file is injected into every Gemini system prompt to provide stable personal
# context that the model cannot infer on its own.
#
# INSTRUCTIONS:
# - Add one fact per line using the "- " bullet format below.
# - Group facts under markdown headings for readability.
# - Keep facts stable and general — not specific tasks or one-off events.
# - This file is never modified by automation. Edit it manually as your context changes.
# - On first deploy, this file is copied to ~/bin/third_brain/facts/base_facts.md.
#   After that, the deployed copy is the live one — edit that directly.
#
# EXAMPLE (replace with your own facts):

## Identity
# - Full name: Jane Smith
# - Personal email: jane@example.com
# - Work email: jane@company.com (employer: Acme Corp)

## Work Domain
# - Works as a software engineer at Acme Corp
# - Primary stack: Python, PostgreSQL, Kubernetes
# - Team focuses on internal tooling and developer productivity

## Home & Personal Interests
# - Runs 4-5 times per week; training for half-marathons
# - Interested in home automation and embedded hardware (ESP32)
# - Follows a plant-based diet

## Technical Skills
# - Languages: Python, Go, Bash
# - Infrastructure: Docker, Kubernetes, Terraform
# - OS: Ubuntu Linux

## Workflow & Preferences
# - Uses Telegram as primary capture interface for tasks and ideas
# - Splits tasks into Work and Home domains
# - Prefers concise, actionable output — no filler
