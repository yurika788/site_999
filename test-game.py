#!/usr/bin/env python3
"""
zombie_shooter_improved.py
Improved top-down zombie shooter (single file, no external assets).
Requires pygame installed (use Python 3.12.x recommended).
"""

import pygame, random, math, sys, time
from collections import deque

# ---------------- Config -----------------
SCREEN_WIDTH = 1152
SCREEN_HEIGHT = 720
FPS = 60

PLAYER_SPEED = 320
BULLET_LIFETIME = 1.6
ZOMBIE_BASE_SPEED = 65

# Visual tweak
MAX_PARTICLES = 400

# Colors
WHITE = (245, 245, 245)
BLACK = (10, 10, 10)
HUD_BG = (18, 18, 20)
RED = (220, 60, 60)
GREEN = (85, 200, 85)
YELLOW = (240, 200, 80)
BLUE = (90, 150, 255)
DARK_GREY = (26, 26, 28)

# ---------------- Utilities -----------------
def clamp(v, a, b):
    return max(a, min(b, v))

def length_sq(v):
    return v.x*v.x + v.y*v.y

def dist(a, b):
    return math.hypot(a.x-b.x, a.y-b.y)

def angle_to(a, b):
    return math.atan2(b.y - a.y, b.x - a.x)

# ---------------- Game objects -----------------
class Gun:
    """Represents a gun type and upgradeable stats."""
    def __init__(self, name, damage, rate, bullet_speed, mag, reload_time, spread=0.0, pellets=1):
        self.name = name
        self.base_damage = damage
        self.base_rate = rate
        self.base_bullet_speed = bullet_speed
        self.base_mag = mag
        self.base_reload_time = reload_time
        self.spread = spread
        self.pellets = pellets

        self.level = 1
        # dynamic stats
        self.damage = damage
        self.rate = rate
        self.bullet_speed = bullet_speed
        self.mag = mag
        self.reload_time = reload_time

    def upgrade_cost(self):
        return 150 * self.level

    def upgrade(self):
        self.level += 1
        self.damage = int(self.damage + self.base_damage * 0.45)
        self.rate = max(0.10, self.rate - self.base_rate * 0.07)
        self.bullet_speed += int(self.base_bullet_speed * 0.12)
        self.mag = max(self.mag, int(self.mag + 2))
        self.reload_time = max(0.3, self.reload_time - 0.05)

class Bullet:
    def __init__(self, pos, vel, damage, life=BULLET_LIFETIME):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.damage = damage
        self.life = life
        self.radius = 4

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        return self.life > 0

class Particle:
    def __init__(self, pos, vel, life, radius, color):
        self.pos = pygame.Vector2(pos)
        self.vel = pygame.Vector2(vel)
        self.life = life
        self.radius = radius
        self.color = color

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt
        # simple friction/gravity
        self.vel *= (1 - 3*dt)
        self.vel.y += 60 * dt
        return self.life > 0

class Zombie:
    SPECS = {
        "walker": {"speed": 1.0, "hp": 18, "score": 10, "color": (90,160,90), "radius":18},
        "runner": {"speed": 1.7, "hp": 10, "score": 14, "color": (200,120,80), "radius":14},
        "brute":  {"speed": 0.7, "hp": 40, "score": 35, "color": (120,100,170), "radius":22}
    }
    def __init__(self, pos, ztype="walker"):
        self.pos = pygame.Vector2(pos)
        self.type = ztype
        spec = Zombie.SPECS[ztype]
        self.speed = ZOMBIE_BASE_SPEED * spec["speed"]
        self.hp = spec["hp"]
        self.max_hp = spec["hp"]
        self.score = spec["score"]
        self.color = spec["color"]
        self.radius = spec["radius"]
        self.dead = False
        self.dir = pygame.Vector2(0,0)
        self.wobble = random.uniform(0, 2*math.pi)

    def update(self, dt, player_pos):
        if self.dead: return
        # homing with slight wobble
        dirv = (player_pos - self.pos)
        if dirv.length_squared() > 0.01:
            dirv = dirv.normalize()
        wob = pygame.Vector2(math.cos(self.wobble), math.sin(self.wobble)) * 0.18
        self.dir = (dirv + wob).normalize()
        self.pos += self.dir * self.speed * dt
        self.wobble += dt * random.uniform(0.5, 2.0)

    def take_damage(self, d):
        self.hp -= d
        if self.hp <= 0:
            self.dead = True
            return True
        return False

class Player:
    def __init__(self, x, y, guns):
        self.pos = pygame.Vector2(x,y)
        self.radius = 18
        self.health = 120
        self.max_health = 120
        self.armor_level = 0
        self.armor_reduction = 0.0  # percent damage reduction
        self.score = 0
        self.guns = guns
        self.current = 0
        self.mag = self.guns[self.current].mag
        self.reload_timer = 0.0
        self.fire_cool = 0.0
        self.is_alive = True
        self.muzzle_timer = 0.0
        self.screen_shake = 0

    def set_weapon(self, idx):
        if 0 <= idx < len(self.guns):
            self.current = idx
            self.mag = self.guns[self.current].mag

    def upgrade_armor_cost(self):
        return 200 * (self.armor_level + 1)

    def upgrade_armor(self):
        self.armor_level += 1
        # linear diminishing returns
        self.armor_reduction = clamp(0.08 * self.armor_level, 0.0, 0.7)

    def take_damage(self, amount):
        effective = amount * (1 - self.armor_reduction)
        self.health -= effective
        self.health = max(0, self.health)
        if self.health <= 0:
            self.is_alive = False

    def update(self, dt, keys):
        if not self.is_alive:
            return
        vel = pygame.Vector2(0,0)
        if keys[pygame.K_w] or keys[pygame.K_UP]: vel.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: vel.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: vel.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: vel.x += 1
        if vel.length_squared() > 0:
            vel = vel.normalize() * PLAYER_SPEED * dt
            self.pos += vel
            self.pos.x = clamp(self.pos.x, self.radius, SCREEN_WIDTH - self.radius)
            self.pos.y = clamp(self.pos.y, self.radius, SCREEN_HEIGHT - self.radius)
        # timers
        self.fire_cool = max(0, self.fire_cool - dt)
        self.reload_timer = max(0, self.reload_timer - dt)
        self.muzzle_timer = max(0, self.muzzle_timer - dt)
        self.screen_shake = max(0, self.screen_shake - 30*dt)

# ---------------- GAME -----------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Zombie Shooter - Improved")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 20)
        self.large_font = pygame.font.SysFont(None, 48)
        self.big_font = pygame.font.SysFont(None, 80)

        # guns: name, damage, rate (s), bullet_speed, mag, reload_time, spread, pellets
        guns = [
            Gun("Pistol", damage=16, rate=0.42, bullet_speed=1100, mag=12, reload_time=0.9, spread=0.02, pellets=1),
            Gun("Shotgun", damage=8, rate=1.0, bullet_speed=800, mag=6, reload_time=1.2, spread=0.28, pellets=7),
            Gun("SMG", damage=9, rate=0.12, bullet_speed=1200, mag=25, reload_time=0.95, spread=0.08, pellets=1),
            Gun("Rifle", damage=40, rate=0.95, bullet_speed=1700, mag=6, reload_time=1.1, spread=0.01, pellets=1),
            Gun("Machine Gun", damage=9, rate=0.8, bullet_speed=1100, mag=100, reload_time=3, spread=0.10, pellets=1)
        ]
        self.player = Player(SCREEN_WIDTH/2, SCREEN_HEIGHT/2, guns)

        # world
        self.bullets = []
        self.zombies = []
        self.particles = deque()
        self.spawn_timer = 0.0
        self.spawn_interval = 0.7
        self.wave = 1
        self.zombies_in_wave = 6
        self.in_wave = True
        self.wave_delay = 2.4
        self.wave_timer = 0
        self.paused = False
        self.shop_open = False
        self.last_kill_time = 0

        # visuals
        self.bg_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.make_background()
        self.screen_shake = 0

        # init first wave
        self.start_wave(1)

    def make_background(self):
        # draw a subtle grid and vignette
        self.bg_surface.fill((14,14,16))
        tile = 48
        for x in range(0, SCREEN_WIDTH, tile):
            pygame.draw.line(self.bg_surface, (18,18,20), (x,0), (x,SCREEN_HEIGHT))
        for y in range(0, SCREEN_HEIGHT, tile):
            pygame.draw.line(self.bg_surface, (18,18,20), (0,y), (SCREEN_WIDTH,y))
        # vignette
        vignette = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for i in range(120):
            alpha = int(6 * i)
            pygame.draw.rect(vignette, (0,0,0,alpha), (-i, -i, SCREEN_WIDTH+i*2, SCREEN_HEIGHT+i*2), border_radius=0)
        self.bg_surface.blit(vignette, (0,0), special_flags=pygame.BLEND_RGBA_SUB)

    def start_wave(self, n):
        self.wave = n
        self.zombies_in_wave = min(6 + n*3, 400)
        self.spawn_interval = max(0.16, 0.7 * (0.95 ** (n-1)))
        self.in_wave = True
        self.spawn_timer = 0
        self.wave_timer = 0

    def spawn_zombie(self):
        side = random.choice(["top","bottom","left","right"])
        margin = 28
        if side == "top":
            pos = (random.uniform(0, SCREEN_WIDTH), -margin)
        elif side == "bottom":
            pos = (random.uniform(0, SCREEN_WIDTH), SCREEN_HEIGHT + margin)
        elif side == "left":
            pos = (-margin, random.uniform(0, SCREEN_HEIGHT))
        else:
            pos = (SCREEN_WIDTH + margin, random.uniform(0, SCREEN_HEIGHT))
        r = random.random()
        if r < 0.08 + (self.wave * 0.002):
            t = "brute"
        elif r < 0.3:
            t = "runner"
        else:
            t = "walker"
        z = Zombie(pos, t)
        self.zombies.append(z)

    def handle_input(self):
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self.shop_open:
                        self.shop_open = False
                    else:
                        self.paused = not self.paused
                if event.key == pygame.K_TAB:
                    self.shop_open = not self.shop_open
                    self.paused = self.shop_open
                if event.key == pygame.K_r:
                    # reload
                    cur = self.player.guns[self.player.current]
                    if self.player.mag < cur.mag and self.player.reload_timer <= 0:
                        self.player.reload_timer = cur.reload_time
                        # simple "instant refill" at timer end
                if event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    idx = int(event.unicode) - 1
                    self.player.set_weapon(idx)
                # shop quick purchases (1..5)
                if self.shop_open and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
                    self.attempt_buy(int(event.unicode))
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1 and not self.paused and self.player.is_alive:
                    self.try_shoot()
                if event.button == 3 and not self.paused and self.player.is_alive:
                    # small heal by spending points
                    if self.player.score >= 100 and self.player.health < self.player.max_health:
                        self.player.score -= 100
                        self.player.health = min(self.player.max_health, self.player.health + 28)
            if event.type == pygame.MOUSEBUTTONUP:
                pass
        return keys

    def try_shoot(self):
        gun = self.player.guns[self.player.current]
        if self.player.reload_timer > 0: return
        if self.player.fire_cool > 0: return
        if self.player.mag <= 0:
            # auto reload if empty
            self.player.reload_timer = gun.reload_time
            return

        # shoot according to gun
        mpos = pygame.Vector2(pygame.mouse.get_pos())
        dir_base = mpos - self.player.pos
        if dir_base.length_squared() == 0: return
        dir_base = dir_base.normalize()
        for p in range(gun.pellets):
            # random spread
            angle = math.atan2(dir_base.y, dir_base.x)
            ang = angle + random.uniform(-gun.spread, gun.spread)
            direction = pygame.Vector2(math.cos(ang), math.sin(ang))
            vel = direction * gun.bullet_speed
            bullet = Bullet(self.player.pos + direction*(self.player.radius+8), vel, gun.damage)
            bullet.radius = 4 if gun.pellets==1 else 3
            self.bullets.append(bullet)
        self.player.mag -= 1
        self.player.fire_cool = gun.rate
        self.player.muzzle_timer = 0.06
        self.player.screen_shake += 6
        # small particle muzzle flash
        for _ in range(6):
            v = pygame.Vector2(random.uniform(-50,50), random.uniform(-50,50)) + dir_base*random.uniform(120,420)
            self.spawn_particle(self.player.pos + dir_base*(self.player.radius+6), v, life=0.12, radius=3, color=YELLOW)

    def spawn_particle(self, pos, vel, life=0.6, radius=3, color=RED):
        if len(self.particles) > MAX_PARTICLES:
            try:
                self.particles.popleft()
            except:
                pass
        self.particles.append(Particle(pos, vel, life, radius, color))

    def update(self, dt, keys):
        if self.paused: return
        # spawn handling
        if self.in_wave and self.zombies_in_wave > 0:
            self.spawn_timer += dt
            while self.spawn_timer >= self.spawn_interval and self.zombies_in_wave > 0:
                self.spawn_timer -= self.spawn_interval
                self.spawn_zombie()
                self.zombies_in_wave -= 1
        elif self.in_wave and self.zombies_in_wave == 0 and all(z.dead for z in self.zombies):
            self.in_wave = False
            self.wave_timer = 0
        if not self.in_wave:
            self.wave_timer += dt
            if self.wave_timer >= self.wave_delay:
                self.start_wave(self.wave + 1)

        # update player
        self.player.update(dt, keys)
        # handle reload finishing
        if self.player.reload_timer > 0:
            self.player.reload_timer -= dt
            if self.player.reload_timer <= 0:
                cur = self.player.guns[self.player.current]
                self.player.mag = cur.mag

        # bullets
        for b in list(self.bullets):
            alive = b.update(dt)
            if not alive or b.pos.x < -50 or b.pos.x > SCREEN_WIDTH+50 or b.pos.y < -50 or b.pos.y > SCREEN_HEIGHT+50:
                try: self.bullets.remove(b)
                except: pass

        # zombies
        for z in self.zombies:
            if not z.dead:
                z.update(dt, self.player.pos)

        # bullet vs zombie collisions
        for b in list(self.bullets):
            for z in list(self.zombies):
                if z.dead: continue
                if dist(b.pos, z.pos) < (b.radius + z.radius):
                    # hit
                    killed = z.take_damage(b.damage)
                    # spawn blood particles
                    for _ in range(6 if killed else 3):
                        angle = random.uniform(0, 2*math.pi)
                        v = pygame.Vector2(math.cos(angle), math.sin(angle)) * random.uniform(80,320)
                        self.spawn_particle(b.pos, v, life=0.6, radius=random.randint(2,4), color=(200,50,50))
                    try: self.bullets.remove(b)
                    except: pass
                    if killed:
                        self.on_kill(z)
                    break

        # zombie-player collisions
        for z in list(self.zombies):
            if z.dead: continue
            if dist(z.pos, self.player.pos) < (z.radius + self.player.radius - 4):
                dmg = 6
                if z.type == "runner": dmg = 8
                elif z.type == "brute": dmg = 14
                self.player.take_damage(dmg)
                # push zombie away a bit
                dirpush = (z.pos - self.player.pos)
                if dirpush.length_squared()>0:
                    dirpush = dirpush.normalize()
                    z.pos += dirpush * 16
                # small hit particles
                for _ in range(6):
                    v = pygame.Vector2(random.uniform(-50,50), random.uniform(-50,50))
                    self.spawn_particle(self.player.pos, v, life=0.4, radius=3, color=(200,120,40))

        # particles update
        for p in list(self.particles):
            alive = p.update(dt)
            if not alive:
                try: self.particles.remove(p)
                except: pass

    def on_kill(self, z):
        z.dead = True
        self.player.score += z.score
        self.player.screen_shake += 8
        self.last_kill_time = time.time()
        # small coin/point particle
        for _ in range(8):
            angle = random.uniform(0, 2*math.pi)
            v = pygame.Vector2(math.cos(angle), math.sin(angle)) * random.uniform(40,240)
            self.spawn_particle(z.pos, v, life=0.8, radius=3, color=(240,220,80))

    def attempt_buy(self, slot):
        # shop layout:
        # 1 - Upgrade current gun
        # 2 - Upgrade other gun (cycle selection)
        # 3 - Buy armor upgrade
        # 4 - Refill health (costly)
        # 5 - Refill ammo for current gun
        curgun = self.player.guns[self.player.current]
        if slot == 1:
            cost = curgun.upgrade_cost()
            if self.player.score >= cost:
                self.player.score -= cost
                curgun.upgrade()
        elif slot == 2:
            # pick a random other gun to upgrade cheaply (or allow choose)
            idx = (self.player.current + 1) % len(self.player.guns)
            cost = self.player.guns[idx].upgrade_cost()
            if self.player.score >= cost:
                self.player.score -= cost
                self.player.guns[idx].upgrade()
        elif slot == 3:
            cost = self.player.upgrade_armor_cost()
            if self.player.score >= cost:
                self.player.score -= cost
                self.player.upgrade_armor()
        elif slot == 4:
            cost = 120
            if self.player.score >= cost and self.player.health < self.player.max_health:
                self.player.score -= cost
                self.player.health = min(self.player.max_health, self.player.health + 70)
        elif slot == 5:
            cost = 60
            cur = self.player.guns[self.player.current]
            if self.player.score >= cost:
                self.player.score -= cost
                self.player.mag = cur.mag

    def draw_player(self, surf, offset):
        p = self.player
        pos = (int(p.pos.x + offset[0]), int(p.pos.y + offset[1]))
        # shadow
        pygame.draw.circle(surf, (8,8,8,120), pos, p.radius+6)
        # body with outline and glow
        pygame.draw.circle(surf, (40,40,55), pos, p.radius+2)
        pygame.draw.circle(surf, (200,200,230), pos, p.radius)
        # eyes/face
        ang = 0
        mpos = pygame.Vector2(pygame.mouse.get_pos()) - pygame.Vector2(offset)
        if (mpos - p.pos).length_squared() > 0.1:
            ang = math.atan2(mpos.y - p.pos.y, mpos.x - p.pos.x)
        eye = pygame.Vector2(math.cos(ang), math.sin(ang)) * 6
        pygame.draw.circle(surf, (20,20,40), (pos[0]+int(-6+eye.x), pos[1]+int(-6+eye.y)), 4)

        # muzzle flash
        if p.muzzle_timer > 0:
            fpos = p.pos + pygame.Vector2(math.cos(ang), math.sin(ang))*(p.radius+8)
            pygame.draw.circle(surf, (255, 220, 120), (int(fpos.x+offset[0]), int(fpos.y+offset[1])), 8)

    def draw_zombie(self, surf, z, offset):
        pos = (int(z.pos.x + offset[0]), int(z.pos.y + offset[1]))
        # shadow
        pygame.draw.circle(surf, (8,8,8,80), pos, z.radius+4)
        # outer
        outline = tuple(max(0,c-40) for c in z.color)
        pygame.draw.circle(surf, outline, pos, z.radius+1)
        pygame.draw.circle(surf, z.color, pos, z.radius)
        # health bar
        hpw = int((z.hp / z.max_hp) * (z.radius*2))
        barx = pos[0] - z.radius
        bary = pos[1] - z.radius - 10
        pygame.draw.rect(surf, (16,16,16), (barx, bary, z.radius*2, 6))
        pygame.draw.rect(surf, (60,220,60), (barx, bary, hpw, 6))

    def draw(self):
        # camera shake offset
        shake = int(self.player.screen_shake + self.screen_shake)
        offset = (random.randint(-shake,shake), random.randint(-shake,shake))
        # background
        self.screen.blit(self.bg_surface, offset)
        # draw particles (behind actors)
        for p in self.particles:
            alpha = int(255 * max(0, min(1, p.life / 0.8)))
            surf = pygame.Surface((p.radius*2+2, p.radius*2+2), pygame.SRCALPHA)
            pygame.draw.circle(surf, p.color + (alpha,), (p.radius+1,p.radius+1), p.radius)
            self.screen.blit(surf, (p.pos.x - p.radius + offset[0], p.pos.y - p.radius + offset[1]))
        # draw zombies
        for z in self.zombies:
            if not z.dead:
                self.draw_zombie(self.screen, z, offset)
        # draw bullets
        for b in self.bullets:
            pygame.draw.circle(self.screen, (255,220,160), (int(b.pos.x+offset[0]), int(b.pos.y+offset[1])), b.radius)
        # player
        self.draw_player(self.screen, offset)
        # HUD
        self.draw_hud()
        # shop overlay
        if self.shop_open:
            self.draw_shop()
        if not self.player.is_alive:
            self.draw_death()

    def draw_hud(self):
        # simple HUD panel
        panel_h = 110
        pygame.draw.rect(self.screen, (16,16,18), (8, 8, 420, panel_h), border_radius=8)
        # Score & wave
        self.screen.blit(self.font.render(f"Points: {int(self.player.score)}", True, WHITE), (20, 14))
        self.screen.blit(self.font.render(f"Wave: {self.wave}", True, WHITE), (20, 36))
        # Health and armor
        health_text = self.font.render(f"HP: {int(self.player.health)}/{self.player.max_health}", True, WHITE)
        self.screen.blit(health_text, (20, 58))
        armor_text = self.font.render(f"Armor Lv: {self.player.armor_level} (-{int(self.player.armor_reduction*100)}%)", True, WHITE)
        self.screen.blit(armor_text, (20, 78))
        # weapon info
        gun = self.player.guns[self.player.current]
        gun_txt = f"{gun.name} Lv{gun.level} | DMG {gun.damage} | Rate {gun.rate:.2f}s | Mag {self.player.mag}/{gun.mag}"
        self.screen.blit(self.font.render(gun_txt, True, WHITE), (20, 98))
        # right side quick info
        self.screen.blit(self.font.render("Controls: WASD Move  LMB Shoot  R Reload  1-4 Switch  TAB Shop", True, (180,180,180)), (460, 18))
        # draw small crosshair
        mx,my = pygame.mouse.get_pos()
        pygame.draw.circle(self.screen, (200,200,200), (mx, my), 6, 1)
        pygame.draw.line(self.screen,(200,200,200),(mx-10,my),(mx+10,my),1)
        pygame.draw.line(self.screen,(200,200,200),(mx,my-10),(mx,my+10),1)

    def draw_shop(self):
        w = 520; h = 320
        x = SCREEN_WIDTH//2 - w//2
        y = SCREEN_HEIGHT//2 - h//2
        pygame.draw.rect(self.screen, (18,18,20), (x,y,w,h), border_radius=12)
        # Title
        title = self.large_font.render("Upgrade Shop", True, (220,220,220))
        self.screen.blit(title, (x+20, y+12))
        # entries
        cur = self.player.guns[self.player.current]
        entries = [
            (f"1) Upgrade current gun ({cur.name}) - Cost: {cur.upgrade_cost()}", f"DMG +{int(cur.base_damage*0.45)}  Rate -{cur.base_rate*0.07:.2f}s"),
            (f"2) Upgrade next gun - Cost: {self.player.guns[(self.player.current+1)%len(self.player.guns)].upgrade_cost()}", "Upgrade another weapon"),
            (f"3) Upgrade Armor - Cost: {self.player.upgrade_armor_cost()}", f"Armor reduces incoming damage"),
            (f"4) Heal 70 HP - Cost: 120", "Instant health"),
            (f"5) Refill Ammo - Cost: 60", "Full magazine for current gun")
        ]
        for i, (line, sub) in enumerate(entries):
            self.screen.blit(self.font.render(line, True, WHITE), (x+24, y+82 + i*36))
            self.screen.blit(self.font.render(sub, True, (180,180,180)), (x+24, y+98 + i*36))

        note = self.font.render("Press number key to buy. Press TAB to exit.", True, (180,180,180))
        self.screen.blit(note, (x+24, y+h-38))

    def draw_death(self):
        s = self.big_font.render("YOU DIED", True, (230,80,80))
        self.screen.blit(s, (SCREEN_WIDTH//2 - s.get_width()//2, SCREEN_HEIGHT//2 - 40))
        t = self.font.render("Press ESC to continue", True, (200,200,200))
        self.screen.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, SCREEN_HEIGHT//2 + 50))

    def run(self):
        last = time.time()
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            keys = self.handle_input()
            self.update(dt, keys)
            # clear screen
            self.screen.fill(DARK_GREY)
            # draw everything
            self.draw()
            pygame.display.flip()

# ---------------- Run -----------------
if __name__ == "__main__":
    game = Game()
    game.run()
