#!/usr/bin/python3

from jupyter_client import KernelManager
import yaml
import sys
import os
import re
from queue import Empty
import pprint


KERNEL_SETUP_CTXS = {}

def kernel_ctx_for(name):
    global KERNEL_SETUP_CTXS
    def _decorator(thing):
        KERNEL_SETUP_CTXS[name] = thing
        return thing
    return _decorator

class empty_ctx:
    def __init__(self):
        pass
    def __enter__(self):
        pass
    def __exit__(self, type, value, traceback):
        pass

def ctx_for(name):
    if name in KERNEL_SETUP_CTXS:
        return KERNEL_SETUP_CTXS[name]()
    else:
        return empty_ctx()

@kernel_ctx_for("python3")
class kernel_ctx_python3:
    def __init__(self):
        pass
    def __enter__(self):
        self.pre_exist = 'PYDEVD_DISABLE_FILE_VALIDATION' in os.environ
        if self.pre_exist:
            self.oldval = os.environ['PYDEVD_DISABLE_FILE_VALIDATION']
        os.environ['PYDEVD_DISABLE_FILE_VALIDATION'] = "1"
    def __exit__(self, type, value, traceback):
        if self.pre_exist:
            os.environ['PYDEVD_DISABLE_FILE_VALIDATION'] = self.oldval
        else:
            del os.environ['PYDEVD_DISABLE_FILE_VALIDATION']

MY_KERNELS = {}
def get_kernel_for(lang_str: str):
    global MY_KERNELS
    if lang_str in MY_KERNELS:
        return MY_KERNELS[lang_str]
    with ctx_for(lang_str):    
        kern = KernelManager(kernel_name=lang_str)
        kern.start_kernel()
    MY_KERNELS[lang_str] = kern
    return kern
def shutdown_kernels():
    for k in MY_KERNELS:
        MY_KERNELS[k].shutdown_kernel()


def evaluate(lang_str: str, content_str: str):
    if not lang_str:
        #print("No language specified; using python3")
        lang_str = "python3"
    km = get_kernel_for(lang_str)
    c = km.client()
    c.wait_for_ready()

    msg_id = c.execute(content_str)
    #print(f"Send execute request: msg_id={msg_id}")
    state = 'busy'
    rslt_type = None
    rslt = None
    while state != 'idle' and c.is_alive():
        try:
            msg = c.get_iopub_msg(timeout=1)
            mtype = msg['header']['msg_type']
            if mtype == 'error':
                rslt_type = 'error'
                rslt = msg['content']['traceback']
            elif mtype == 'stream':
                pass
            elif mtype == 'execute_result':
                rslt_type = 'result'
                rslt = msg['content']['data']
            elif mtype == 'status':
                pass # Note it still sets execution_state later
            elif mtype == 'execute_input':
                pass
            else:
                pprint.pprint(msg)
            
            if 'content' not in msg:
                continue
            content = msg['content']
            if 'data' in content:
                data = content['data']
                #print("Kernel returned data:")
                #print(data)

            if 'execution_state' in content:
                state = content['execution_state']
        except Empty:
            #print("Timeout wating for kernel, going 'round again...")
            pass
    if rslt_type == 'error':
        raise ValueError(rslt)
    if rslt_type == 'result':
        # https://jupyter-client.readthedocs.io/en/latest/messaging.html#execution-results
        # it's a dict by mime-type; will always at least include text/plain.
        # I think; docs are a bit off.
        rslt = rslt['text/plain']
        # I seriously doubt it's actually yaml (or json)
        # In which case, I'd have to load it somehow, then find how to turn an
        # object into yaml events. Worst case would be to serialize to yaml and
        # then parse for events, but eww.
        #
        # Also, do different kernels use different formats? That's be a royal pain. 
        return yaml.parse(rslt)
    if rslt_type == None:
        return None
    raise ValueError(f"Can't handle result type {rslt_type}")


def trim_start_end(events, is_mapping: bool, document_only: bool = False):
    trim_count = 0
    buffer = []
    phase = 'head'
    for event in events:
        if phase == 'head':
            trim_count += 1
            if isinstance(event, yaml.SequenceStartEvent):
                if is_mapping:
                    raise ValueError("Expected a Mapping, got a Sequence")
                phase = 'tail'
            if isinstance(event, yaml.MappingStartEvent):
                if not is_mapping:
                    raise ValueError("Expected a Sequence, got a Mapping")
                phase = 'tail'
            if isinstance(event, yaml.DocumentStartEvent) and document_only:
                phase = 'tail'
        elif phase == 'tail':
            buffer.append(event)
            if len(buffer) > trim_count:
                ret = buffer.pop(0)
                if isinstance(ret, yaml.DocumentEndEvent):
                    raise ValueError("Interpolated item had multiple yaml documents.")
                yield ret

SUBST_KEY_RE=re.compile(r'\(([*!@])(\S+)?\s(.*)\1\)\s*', re.DOTALL)

def maybe_do_subst(event, context_event):
    if not isinstance(event, yaml.ScalarEvent):
        return False, False, [event]
    if not isinstance(event.value, str):
        return False, False, [event]
    val: str = event.value
    match = SUBST_KEY_RE.fullmatch(val)
    if not match:
        return False, False, [event]
    type_char = match.group(1)
    lang_str = match.group(2)
    content_str = match.group(3)

    eval_result_events = evaluate(lang_str, content_str)

    if type_char == '*':
        # Evaluate but don't put anything in the doc. Basically an empty splat.
        if eval_result_events != None:
            raise ValueError("no-return substitution returned a value")
        return True, isinstance(context_event, yaml.MappingStartEvent), []
    elif type_char == '@':
        myevents = eval_result_events
        splat_mapping = isinstance(context_event, yaml.MappingStartEvent)
        myevents = trim_start_end(myevents, splat_mapping)
        return True, splat_mapping, myevents
    elif type_char == '!':
        return True, False, trim_start_end(eval_result_events, False, True)
    raise AssertionError("Fell of the end of a function. This should not be possible.")

def do_template(yaml_stream):
    context_event_stack = []
    def maybe_note_stack(event):
        name = type(event).__name__
        if name.endswith('StartEvent'):
            context_event_stack.append(event)
        if name.endswith('EndEvent'):
            context_event_stack.pop()
    prev_event = None
    for event in yaml_stream:
        maybe_note_stack(event)
        context_event = context_event_stack[-1] if len(context_event_stack) > 0 else None
        did_subst, remove_prev, events = maybe_do_subst(event, context_event)
        if did_subst:
            if not remove_prev:
                yield prev_event
            prev_event = None
            for ee in events:
                yield ee
        else:
            if prev_event:
                yield prev_event
            prev_event = event
    if prev_event:
        yield prev_event
        prev_event = None

def prune_empty_docs(events):
    """
    The parser generates an empty value element for an empty doc, and the serializer expect that.
    If we've removed all elements (the only thing present was a "(* ... *)" string), just
    remove the whole doc.
    """
    prev_event = None
    for event in events:
        if isinstance(event, yaml.DocumentEndEvent) and isinstance(prev_event, yaml.DocumentStartEvent):
            prev_event = None
            continue
        if prev_event != None:
            yield prev_event
        prev_event = event
    if prev_event != None:
        yield prev_event

def run():
    for file in sys.argv[1:]:
        with open(file, 'r') as ff:
            modified_stream = do_template(yaml.parse(ff))
            modified_stream = prune_empty_docs(modified_stream)
            result = yaml.emit(modified_stream)
            print(result)

if __name__ == '__main__':
    try:
        run()
    finally:
        shutdown_kernels()
