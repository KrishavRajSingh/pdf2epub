#!/bin/zsh
# Run every self-check. Exit 1 if any fails. Used by the pre-push hook and scripts/deploy.sh.
cd "${0:A:h}/.."
fail=0
for t in test_*.py; do
  out=$(python3 "$t" 2>&1); rc=$?
  out=$(print -r -- "$out" | grep -v Warning)
  if [[ $rc -ne 0 || "$out" == *Traceback* || "$out" == *FAIL* || "$out" == *AssertionError* ]]; then
    print -r -- "FAIL $t"; print -r -- "$out" | tail -15; fail=1
  else
    print -r -- "ok   $t"
  fi
done
exit $fail
