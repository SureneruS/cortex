#!/bin/bash
# Cortex plugin hook: SessionStart
# Registers session in Cortex registry, injects knowledge context
exec nova-session-start
