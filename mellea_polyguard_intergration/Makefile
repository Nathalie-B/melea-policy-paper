.PHONY: guardrails-install guardrails-setup guardrails-all

guardrails-install:
	pip install guardrails-ai

guardrails-setup:
	guardrails configure
	guardrails hub install hub://guardrails/detect_pii
	guardrails hub install hub://guardrails/llamaguard_7b

guardrails-all: guardrails-install guardrails-setup
