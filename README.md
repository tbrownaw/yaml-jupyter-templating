# What is this?

This is an object-based template engine for YAML, built on top of Jupyter.

It uses a Jupyter kernel to execute code blocks from specially-formatted string values, and then inserts the returned object into the object tree where the code was before re-serializing the result back to YAML.

## What's wrong with text-based templating?

TODO: go find that rant about the C preprocessor and I think it was hygenic macros?

TODO: proper description of indent-level issues in for example Helm.

# Run

Make sure Jupyter is installed, and has at least the `python3` kernel that I think is in the default install.

```
python3 -mvenv env
. env/bin/activate
pip install -r requirements.lock
python3 run_template.py sample.yaml
```

# Syntax

This can do three (four) things.

* Execute code with no return value:
  ```
  (* code goes here *)
  ```
* Execute code and insert the result object:
  ```
  key: (! x = {}; x['foo'] = bar; x !)
  ```
* Splat an array or oject
   ```
   - arrayval_1
   - (@ [ "arrayval_2", "arrayval_3" ] @)
   ---
   key1: val1
   this_key_is_arbitrary_and_ignored: |
     (@
     x = {'splatkey_1': 'splatval_1'}
     x['splatkey_2'] = 'splatval_2'
     x
     @)
   key4: val4
   ```

If you don't want the default `python3` kernel (or just want to be explicit), you can specify which one to use:
```
key: |
  (!kernelname
  code goes here
  !)
```

# TODO

- make it recurse
- validate a few other kernels
  - xpython
  - the .NET kernel (I don't think I see this in `apt`)
  - at least one Java kernel
- try a complex object with the `python3` kernel, see how it serializes
- refactor the globals into class objects
