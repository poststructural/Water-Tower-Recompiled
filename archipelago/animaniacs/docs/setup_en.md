# Animaniacs: The Great Edgar Hunt — Archipelago setup

You need the recompiled game from
[Animaniacs Remastered](https://gitlab.com/unowa001/animaniacs-remastered) (Vulkan build)
and your own copy of the Xbox game.

1. Install `animaniacs.apworld` (double-click it, or copy it into Archipelago's
   `custom_worlds` folder).
2. Make a YAML with the Options Creator and generate a seed as usual.
3. In the launcher's Archipelago tab, turn the session on and fill in the room's
   address and your slot name, then press Play. Or start the game yourself:

   ```
   Animaniacs.exe --ap-server archipelago.gg:38281 --ap-slot YourName
   ```

   A password goes in `ANI_AP_PASSWORD` (environment) instead of the command line.
4. Start a **new game** for each seed. The game connects by itself; there is no
   separate client window.

Every Edgar, ACME letter, script page and quest item you pick up sends a check, and
so do the collectibles and apples if your YAML says so. The Edgars you receive open
the movie sets (the hub's doors want 4, 9, 12 and 25) and CC Deville's boss game (36).
