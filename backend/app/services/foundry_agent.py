"""
Agent orchestration via Azure AI Foundry Agent Service (v2 SDK).

IMPORTANT: as of Aug 26 2026 the old threads/runs/messages API is
retired. This uses the current versioned-agent + Responses API model:
  1. create a version of our agent with a PromptAgentDefinition (tools attached)
  2. route the agent's endpoint to that version
  3. talk to it via project_client.get_openai_client(agent_name=...).responses.create(...)
  4. client-side execute any function_call items the model emits, loop
     until it stops asking for more tool calls

Auth is Entra ID via DefaultAzureCredential (local: `az login`; deployed:
managed identity) -- NOT an API key.

Fallback: when FOUNDRY_PROJECT_ENDPOINT isn't set, falls back to a
direct Azure OpenAI chat-completions call with the same tool set
implemented as a simple client-side loop (see generation.py) -- weaker
(no Foundry-side agent versioning/observability) but keeps the whole
app runnable without the Foundry project being configured yet.
"""
import json
from app.config import get_settings

_project_client = None
_agent_ready = False


def _get_project_client():
    global _project_client
    if _project_client is None:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
        settings = get_settings()
        credential = DefaultAzureCredential()
        _project_client = AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=credential)
    return _project_client


def _ensure_agent_version(tools: list):
    """Creates (or re-creates) a version of our agent with the given tool
    set and routes the agent's endpoint to it. Called once per process
    per distinct tool set -- feature functions in agent.py each pass the
    specific tools they need."""
    from azure.ai.projects.models import (
        PromptAgentDefinition, AgentEndpointConfig, ProtocolConfiguration,
        ResponsesProtocolConfiguration, VersionSelector, FixedRatioVersionSelectionRule,
    )
    settings = get_settings()
    client = _get_project_client()

    version = client.agents.create_version(
        agent_name=settings.foundry_agent_name,
        definition=PromptAgentDefinition(
            model=settings.azure_openai_chat_deployment,  # deployment name, not raw model id
            instructions=(
                "You are a research assistant that answers strictly from the "
                "tools provided (which query the user's uploaded papers). "
                "Never use outside knowledge. Always call a tool before answering "
                "a factual question about the papers."
            ),
            tools=tools,
        ),
    )
    client.agents.update_details(
        agent_name=settings.foundry_agent_name,
        agent_endpoint=AgentEndpointConfig(
            version_selector=VersionSelector(
                version_selection_rules=[
                    FixedRatioVersionSelectionRule(agent_version=version.version, traffic_percentage=100),
                ]
            ),
            protocol_configuration=ProtocolConfiguration(responses=ResponsesProtocolConfiguration()),
        ),
    )
    return version


def run_agent(input_text: str, tool_defs: list, tool_impls: dict[str, callable], max_tokens: int = 900) -> str:
    """
    tool_defs: list of azure.ai.projects.models.FunctionTool definitions
    tool_impls: {tool_name: python_callable(**kwargs) -> str}
    Runs the agent, client-side-executing any function_call items until
    the model produces a final text answer.
    """
    settings = get_settings()
    if not settings.use_foundry_agent:
        from app.services import generation
        return generation.generate(
            "You answer using only the provided context.", input_text, max_tokens=max_tokens
        )

    from openai.types.responses.response_input_param import FunctionCallOutput

    _ensure_agent_version(tool_defs)
    client = _get_project_client()

    with client.get_openai_client(agent_name=settings.foundry_agent_name) as openai_client:
        response = openai_client.responses.create(input=input_text)

        # Loop until the model stops asking for tool calls.
        for _ in range(6):  # hard cap to avoid runaway loops
            calls = [item for item in response.output if item.type == "function_call"]
            if not calls:
                break
            outputs = []
            for call in calls:
                impl = tool_impls.get(call.name)
                if impl is None:
                    result = f"Error: unknown tool '{call.name}'"
                else:
                    try:
                        result = impl(**json.loads(call.arguments))
                    except Exception as e:
                        result = f"Error running tool '{call.name}': {e}"
                outputs.append(FunctionCallOutput(
                    type="function_call_output", call_id=call.call_id, output=str(result),
                ))
            response = openai_client.responses.create(input=outputs, previous_response_id=response.id)

        return response.output_text
