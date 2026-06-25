# Checkpoints

This server bundle includes the two default pretrained files used by the
controller:

- `PT_zeroshot_painn.pt`: AdsorbDiff PaiNN diffusion sampling checkpoint.
- `gemnet_oc_base_s2ef_2M.pt`: GemNet-OC relaxation checkpoint.

The controller searches this directory automatically before falling back to
case-local `checkpoints/` folders.
