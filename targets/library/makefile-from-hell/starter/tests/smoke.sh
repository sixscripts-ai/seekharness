#!/bin/sh
set -eu
out="$(./build/calc 7 5)"
[ "$out" = "sum=12 product=35" ]
echo TEST_PASS
