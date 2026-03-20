#!/bin/bash

demo=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
echo ${demo}
export NG_SCRIPT_DIR="${demo}"
base=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && cd .. &> /dev/null && pwd )
echo ${base}
export NG_BASE_DIR="${base}"
