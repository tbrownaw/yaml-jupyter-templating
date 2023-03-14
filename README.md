# What is this?

This is an object-based template engine for YAML, built on top of Jupyter.

It uses a Jupyter kernel to execute code blocks from specially-formatted string values, and then inserts the returned object into the object tree where the code was before re-serializing the result back to YAML.

## What's wrong with text-based templating?

TODO: go find that rant about the C preprocessor and I think it was hygenic macros?

TODO: proper description of indent-level issues in for example Helm.

# TODO

- make it recurse
- validate a few other kernels
  - xpython
  - the .NET kernel (I don't think I see this in `apt`)
  - at least one Java kernel
- try a complex object with the `python3` kernel, see how it serializes
- refactor the globals into class objects
