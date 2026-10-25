#!/usr/bin/env bash
# run_all.sh
#
# Runs every BuzDim script in the correct order. Each script's output is
# shown on screen and also saved as a trace file in output/.
#
# Run from the project root, with the buzdim environment active:
#     conda activate buzdim
#     bash run_all.sh

# Stop at the first error, including errors inside a pipe.
set -e
set -o pipefail

mkdir -p output

run_step() {
    # $1 is the script name, $2 is the trace file to save its output to
    echo ""
    echo "############################################################"
    echo "Running src/$1"
    echo "############################################################"
    # -u turns off output buffering, so Python's own messages and the
    # reasoner's messages appear in the trace in the order they happened.
    python -u "src/$1" 2>&1 | tee "output/$2"
}

run_step build_ontology.py   build_trace.txt
run_step populate.py         populate_trace.txt
run_step rules.py            rules_trace.txt
run_step forward_chainer.py  forward_chaining_trace.txt
run_step backward_chainer.py backward_chaining_trace.txt
run_step queries.py          queries_trace.txt

echo ""
echo "All scripts finished. Traces are saved in output/."
