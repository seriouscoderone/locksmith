#!/usr/bin/env bash

# Loop from 1 to 100
for i in {1..100}
do
  kli incept --name locksmith --alias "Test-${i}" --icount 1 --isith "1" --ncount 1 --nsith "1" --toad 0 --transferable
done