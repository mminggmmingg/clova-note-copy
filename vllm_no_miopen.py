import torch

# 이 부분은 부모/자식 프로세스 모두 실행되어야 함
torch.backends.cudnn.enabled = False

print(
    "[clova-note] MIOpen disabled:",
    not torch.backends.cudnn.enabled,
    flush=True,
)

def run():
    from vllm.entrypoints.cli.main import main
    main()

if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()
    run()
