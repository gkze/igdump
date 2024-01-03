{
  description = "Instagram Dumper";

  inputs = {
    # Use latest nixpkgs
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    # Flake helper
    fp.url = "github:hercules-ci/flake-parts";

    # Unified polyglot source formatter
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # Nix development shell helper
    devshell = {
      url = "github:numtide/devshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = inputs: inputs.fp.lib.mkFlake { inherit inputs; } {
    # All officially supported systems
    systems = inputs.nixpkgs.lib.systems.flakeExposed;

    # Attributes here have systeme above suffixed across them
    perSystem = { system, config, pkgs, lib, ... }: {
      # Inject Nixpkgs with our config
      # https://nixos.org/manual/nixos/unstable/options#opt-_module.args
      _module.args.pkgs = import inputs.nixpkgs {
        inherit system;
        overlays = [ inputs.devshell.overlays.default ];
        config.allowUnfree = true;
      };

      # Unified source formatting
      formatter = inputs.treefmt-nix.lib.mkWrapper pkgs {
        projectRootFile = "flake.nix";
        programs = {
          # Python
          ruff.enable = true;
          isort.enable = true;
          # Nix
          nixpkgs-fmt.enable = true;
          deadnix.enable = true;
        };
      };

      # Development shell
      devShells.default = pkgs.devshell.mkShell {
        name = "nixcfg";
        packages = with pkgs; [ python3 pyupgrade ];
      };
    };
  };
}
