"""Version-tested SDK boundary. No model is instantiated by this module."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Callable
from importlib.metadata import version

def run_guarded_workflow(action: dict,dispatch: Callable[[dict],dict]) -> dict:
    if version('openjiuwen')!='0.1.19.post2':raise ValueError('openJiuwen runtime version differs from pin')
    from openjiuwen.core.workflow import Workflow, WorkflowCard, Start, End, WorkflowComponent, create_workflow_session
    class GuardedTool(WorkflowComponent):
        async def invoke(self,inputs,session,context):
            # Dispatch is a host closure. No tools or arbitrary paths come from the SDK.
            return {'result':dispatch(inputs['action'])}
    async def invoke():
        flow=Workflow(card=WorkflowCard(id='vli_guarded_local',name='vli_guarded_local',version='0.1.0'))
        flow.set_start_comp('start',Start(),inputs_schema={'action':'${action}'})
        flow.add_workflow_comp('guarded_tool',GuardedTool(),inputs_schema={'action':'${start.action}'})
        flow.set_end_comp('end',End(),inputs_schema={'result':'${guarded_tool.result}'})
        flow.add_connection('start','guarded_tool');flow.add_connection('guarded_tool','end')
        output=await flow.invoke({'action':action},create_workflow_session())
        if str(output.state.value)!='COMPLETED':raise ValueError('SDK workflow did not complete')
        return output.result['output']['result']
    return asyncio.run(invoke())
