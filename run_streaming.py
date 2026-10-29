import torch

# Strix Halo gfx1151 MIOpen Conv2D 문제 우회
torch.backends.cudnn.enabled = False

print(
    "[clova-note] MIOpen disabled:",
    not torch.backends.cudnn.enabled,
    flush=True,
)

def run():
    from qwen_asr.cli.demo_streaming import main
    main()

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    run()
