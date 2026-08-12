# Source and publication provenance

## Idea source

- Feishu root:
  <https://icnbwz7kd1ui.feishu.cn/wiki/WdKEw16UPiVugFkF6NWcowDtnqh>
- Feishu experiment report:
  <https://icnbwz7kd1ui.feishu.cn/wiki/XRB7wg9pKin6rvk9WsYciEf6npe>
- Steering archive base:
  `3ccc651085e17aebd6341ebc5bdebea21eaf9d9a`
- Proposal snapshot:
  `f0f0abe412f6e5926e798cafec8db17e75e184ad`

The original task text supplied by the user is preserved as
`docs/original_phase1_request.txt` in the standalone publication.

## Implementation lineage

- Initial pilot implementation: `9eb7478f893b50710f7ad2b20b01b55ca7737e14`
- robosuite/headless fix: `bbef2c38fb1b26bf290e2c288377c633a1e49f2c`
- hidden gripper diagnosis: `d2aaa968ca5b238bec06e9754ab97deec1d7a3b5`
- normalized branch contract: `24d7cf3df4969275385ba977462c47e326211ae8`
- compact result record: `e6c9e0253325c2cf0813007464ed0a92ccd9948c`

## Evidence inclusion policy

The standalone GitHub publication contains every persisted run artifact under
the R22-P19 output namespace, including failed smoke attempts. It excludes the
two large LIBERO HDF5 datasets, external LIBERO assets, Python environments,
model weights, credentials, and unrelated steering-repository history.

Every publication file is covered by the root `SHA256SUMS` manifest. Raw
JSONL branch and trace evidence is marked generated in `.gitattributes` to
keep GitHub code statistics and diffs useful without hiding the data.
