from guardrails import Guard, OnFailAction
from guardrails.hub import LlamaGuard7B
from guardrails.hub import DetectPII


GENERAL_SAFETY_GUARD = Guard().use(LlamaGuard7B, on_fail=OnFailAction.EXCEPTION)
PII_GUARD = Guard().use(
    DetectPII, ["EMAIL_ADDRESS", "PHONE_NUMBER"], "exception"
)
DETECT_SELF_HARM_GUARD = Guard().use(
    LlamaGuard7B, 
    policies=[LlamaGuard7B.POLICY__NO_ENOURAGE_SELF_HARM], 
    on_fail=OnFailAction.EXCEPTION
)


#Agent-User Interaction Guard
def safe_llm_output_validation(agent_response: str) -> None:
    try:
        GENERAL_SAFETY_GUARD.validate(agent_response)  # Guardrail passes
    except Exception as e:
       #run obligation checks or return error, handle with general guard -> obligation flow
       print("Unexpected: ",e)

#Run after every User Input
def self_harm_detection(user_input: str) -> None:
    try:
        DETECT_SELF_HARM_GUARD.validate(user_input)  # Guardrail passes
    except Exception as e:
       #run obligation checks or return error, handle with general guard -> obligation flow
       print("Unexpected: ",e)

#Run on every tool and interaction instance
def PII_detection(agent_response: str) -> None:
    try:
        PII_GUARD.validate(agent_response)  # Guardrail passes
    except Exception as e:
       #run obligation checks or return error, handle with general guard -> obligation flow
       print("Unexpected: ",e)




