#!/bin/bash
set -x #echo on

echo "graphs:" > graphs.yaml
for format in ttl trig nt rdfxml
do
    riot            --out=$format input.ttl  > sample.$format
    riot --compress --out=$format input.ttl  > sample.$format.gz
    echo "  - name: sample_$format"      >> graphs.yaml
    echo "    file:"                     >> graphs.yaml
    echo "    - sample.$format"          >> graphs.yaml
    echo "  - name: sample_${format}_gz" >> graphs.yaml
    echo "    file:"                     >> graphs.yaml
    echo "    - sample.$format.gz"       >> graphs.yaml
done


