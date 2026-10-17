# Animaniacs: The Great Edgar Hunt — Archipelago setup

You need the recompiled game from
[AnimaniacsRecompiled](https://github.com/Unowa001/AnimaniacsRecompiled) (Vulkan build)
and your own copy of the Xbox game.

1. Install `animaniacs.apworld` (double-click it, or copy it into Archipelago's
   `custom_worlds` folder).
2. Make a YAML with the Options Creator and generate a seed as usual.
3. Start the game with the room's address and your slot name:

   ```
   Animaniacs.exe --ap-server archipelago.gg:38281 --ap-slot YourName
   ```

   A password goes in `ANI_AP_PASSWORD` (environment) instead of the command line.
4. Start a **new game** for each seed. The game connects by itself; there is no
   separate client window.

Every Edgar you pick up sends a check. The Edgars you receive open the movie sets.
