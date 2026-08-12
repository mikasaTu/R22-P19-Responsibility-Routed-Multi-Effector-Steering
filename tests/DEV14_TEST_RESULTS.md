# dev14 verification receipt

Final verification was executed in the actual LIBERO runtime:

```text
Python: /mnt/cpfs/zbl-cpfs-new/USERS/leon/envs/libero-original/bin/python
Source HEAD: e6c9e0253325c2cf0813007464ed0a92ccd9948c

...                                                                      [100%]
3 passed in 1.45s
CPFS_RESULT_CONTRACT_OK
PAI_REGISTRY_R22P19_MATCHES=0
```

Additional persisted checks:

- `smoke-v5-20260813/SMOKE_COMPLETE.json`:
  `implementation_smoke_pass=true`
- `signal-v1-20260813/EVALUATION_COMPLETE.json`:
  `status=EVALUATION_COMPLETE`
- `signal-v1-20260813/decision.json`:
  `decision=LIBERO_SUBSTRATE_NO_GO`
- `signal-v1-20260813/ACT_PAI_SKIPPED.json`:
  `pai_job_created=false`
- `signal-v1-20260813/VERIFICATION.json`:
  independent result and SHA256 readback passed
