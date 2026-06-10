"use client";

import { Html, Line, OrbitControls, PerspectiveCamera, Text } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { Component, memo, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Mesh } from "three";
import type { ArenaEvent, PlayerSeat, ViewMode } from "@/types/game";
import { replaceWithFirstPerson } from "@/lib/tts-queue";
import { extractRelationships } from "@/lib/relationships";
import { ArenaStageFallback } from "./arena-stage-fallback";

type ArenaStageProps = {
  players: PlayerSeat[];
  currentEvent: ArenaEvent;
  viewMode: ViewMode;
  selectedSeat: number;
  events?: ArenaEvent[];
  onBubbleClick?: (event: ArenaEvent) => void;
};

type CanvasErrorBoundaryProps = ArenaStageProps & {
  children: ReactNode;
  onBubbleClick?: (event: ArenaEvent) => void;
};

type CanvasErrorBoundaryState = {
  failed: boolean;
};

const roleColors: Record<string, string> = {
  间谍: "#f05cff",
  狼人: "#f05cff",
  HR总监: "#4dc7ff",
  预言家: "#f8c47a",
  CEO: "#4dc7ff",
  安保主管: "#8b5cf6",
  法务总监: "#4de7db",
  普通员工: "#56e3ff"
};

class CanvasErrorBoundary extends Component<CanvasErrorBoundaryProps, CanvasErrorBoundaryState> {
  state: CanvasErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): CanvasErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch() {
    // Swallow — fallback UI handles it
  }

  render() {
    if (this.state.failed) {
      return (
        <ArenaStageFallback
          players={this.props.players}
          currentEvent={this.props.currentEvent}
          viewMode={this.props.viewMode}
          selectedSeat={this.props.selectedSeat}
          events={this.props.events}
          reason="error"
        />
      );
    }

    return this.props.children;
  }
}

function SeatNode({
  player,
  index,
  total,
  currentEvent,
  viewMode,
  selectedSeat,
  teammates,
  onBubbleClick
}: {
  player: PlayerSeat;
  index: number;
  total: number;
  currentEvent: ArenaEvent;
  viewMode: ViewMode;
  selectedSeat: number;
  teammates: number[];
  onBubbleClick?: (event: ArenaEvent) => void;
}) {
  const meshRef = useRef<Mesh>(null);
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  const radius = 4.25;
  const x = Math.cos(angle) * radius;
  const z = Math.sin(angle) * radius;
  const isActor = currentEvent.speaker === player.name;
  const isTarget = currentEvent.target === player.name;
  const isSelected = viewMode === "agent" && selectedSeat === player.seat;
  const showRole = viewMode === "god" || (viewMode === "agent" && (player.seat === selectedSeat || teammates.includes(player.seat)));
  const color = showRole ? (roleColors[player.role] ?? "#56e3ff") : "#56e3ff";

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const pulse = isActor || isTarget || isSelected ? Math.sin(clock.elapsedTime * 4) * 0.08 : 0;
    meshRef.current.scale.setScalar(player.alive ? 1 + pulse : 0.74);
  });

  const inwardAngle = angle + Math.PI;
  const deskOffsetX = Math.cos(inwardAngle) * 0.9;
  const deskOffsetZ = Math.sin(inwardAngle) * 0.9;

  return (
    <group position={[x, 0.4, z]}>
      {/* 座位前的笔记本电脑 */}
      <group position={[deskOffsetX, -0.52, deskOffsetZ]} rotation={[0, inwardAngle + Math.PI, 0]}>
        {/* 电脑底座/键盘 */}
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
          <boxGeometry args={[0.44, 0.3, 0.02]} />
          <meshStandardMaterial color="#1a1a2a" metalness={0.7} roughness={0.3} />
        </mesh>
        {/* 屏幕 */}
        <mesh position={[0, 0.17, -0.14]} rotation={[-0.3, 0, 0]}>
          <boxGeometry args={[0.42, 0.28, 0.015]} />
          <meshStandardMaterial color="#0a0a14" metalness={0.5} roughness={0.2} />
        </mesh>
        {/* 屏幕发光面 */}
        <mesh position={[0, 0.17, -0.133]} rotation={[-0.3, 0, 0]}>
          <planeGeometry args={[0.36, 0.22]} />
          <meshBasicMaterial color={color} transparent opacity={player.alive ? 0.35 : 0.08} />
        </mesh>
      </group>
      {/* 咖啡杯 */}
      <group position={[deskOffsetX + Math.cos(inwardAngle + 0.6) * 0.35, -0.52, deskOffsetZ + Math.sin(inwardAngle + 0.6) * 0.35]}>
        <mesh>
          <cylinderGeometry args={[0.055, 0.045, 0.11, 16]} />
          <meshStandardMaterial color="#e8e0d4" metalness={0.1} roughness={0.7} />
        </mesh>
        {/* 咖啡液面 */}
        <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.05, 16]} />
          <meshStandardMaterial color="#3a2010" roughness={0.9} />
        </mesh>
      </group>
      <mesh position={[0, -0.55, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.48, 0.88, 80]} />
        <meshBasicMaterial color={color} transparent opacity={player.alive ? 0.5 : 0.16} />
      </mesh>
      <mesh position={[0, -0.56, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.62, 72]} />
        <meshBasicMaterial color={color} transparent opacity={player.alive ? 0.12 : 0.05} />
      </mesh>
      <mesh ref={meshRef} castShadow>
        <cylinderGeometry args={[0.28, 0.42, 0.88, 48]} />
        <meshStandardMaterial color={player.alive ? color : "#2f3c55"} emissive={color} emissiveIntensity={player.alive ? 0.36 : 0.04} metalness={0.42} roughness={0.28} />
      </mesh>
      <mesh position={[0, 0.72, 0]} castShadow>
        <sphereGeometry args={[0.28, 40, 40]} />
        <meshStandardMaterial color={player.alive ? "#bdf4ff" : "#546178"} emissive={player.alive ? color : "#000000"} emissiveIntensity={0.32} roughness={0.2} />
      </mesh>
      {showRole && <RoleDecoration role={player.role} alive={player.alive} />}
      {(isActor || isTarget || isSelected) && (
        <mesh position={[0, -0.58, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.92, 1.04, 96]} />
          <meshBasicMaterial color={isTarget ? "#ff4f87" : "#4dc7ff"} transparent opacity={0.92} />
        </mesh>
      )}
      <Html center distanceFactor={7.6} position={[0, 1.54, 0]}>
        <div className="seat-label">
          <strong>{player.name}</strong>
          <span>{showRole ? player.role : (player.alive ? "存活" : "出局")}</span>
        </div>
        {isActor && currentEvent.text && (currentEvent.type === "model_call" || currentEvent.type === "decision") && currentEvent.text !== "模型调用" && (
          <div
            className="speech-bubble cursor-pointer"
            onClick={(e) => { e.stopPropagation(); onBubbleClick?.(currentEvent); }}
          >
            <div className="bubble-header">
              <span>{player.name} · {currentEvent.action ?? "发言"}</span>
            </div>
            <div className="bubble-body">
              {(() => {
                const t = replaceWithFirstPerson(currentEvent.text, selectedSeat);
                return t.length > 80 ? t.slice(0, 80) + "…" : t;
              })()}
            </div>
          </div>
        )}
      </Html>
    </group>
  );
}

function ActionBeam({ players, currentEvent }: { players: PlayerSeat[]; currentEvent: ArenaEvent }) {
  const points = useMemo(() => {
    const actorIndex = players.findIndex((player) => player.name === currentEvent.speaker);
    const targetIndex = players.findIndex((player) => player.name === currentEvent.target);
    if (actorIndex < 0 || targetIndex < 0) return null;
    const toPosition = (index: number) => {
      const angle = (Math.PI * 2 * index) / players.length - Math.PI / 2;
      return [Math.cos(angle) * 4.25, 0.28, Math.sin(angle) * 4.25] as const;
    };
    return [toPosition(actorIndex), toPosition(targetIndex)];
  }, [players, currentEvent.speaker, currentEvent.target]);

  if (!points) return null;

  return (
    <group>
      <mesh position={[0, 1.72, 0]}>
        <sphereGeometry args={[0.08, 20, 20]} />
        <meshBasicMaterial color="#ff4f87" />
      </mesh>
      {points.map((point, index) => (
        <mesh key={index} position={point}>
          <sphereGeometry args={[0.07, 20, 20]} />
          <meshBasicMaterial color={index === 0 ? "#4dc7ff" : "#ff4f87"} />
        </mesh>
      ))}
      <Text position={[0, 2.06, 0]} fontSize={0.2} color="#f8c47a" anchorX="center">
        {`${currentEvent.action ?? "行动"} -> ${currentEvent.target ?? "目标"}`}
      </Text>
    </group>
  );
}

function RelationshipLines({ players, events }: { players: PlayerSeat[]; events: ArenaEvent[] }) {
  const relationships = useMemo(() => {
    const names = players.map((p) => p.name);
    return extractRelationships(events, names, players);
  }, [players, events]);

  const toPosition = (name: string): [number, number, number] | null => {
    const index = players.findIndex((p) => p.name === name);
    if (index < 0) return null;
    const angle = (Math.PI * 2 * index) / players.length - Math.PI / 2;
    return [Math.cos(angle) * 4.25, 0.12, Math.sin(angle) * 4.25];
  };

  const colorMap = { trust: "#4dc7ff", suspicion: "#ff4f87", interaction: "#f8c47a" };
  const dashMap = { trust: false, suspicion: false, interaction: true };

  return (
    <group>
      {relationships.map((rel) => {
        const from = toPosition(rel.from);
        const to = toPosition(rel.to);
        if (!from || !to) return null;
        const opacity = Math.min(0.7, 0.2 + rel.weight * 0.08);
        return (
          <Line
            key={`${rel.from}-${rel.to}-${rel.type}`}
            points={[from, to]}
            color={colorMap[rel.type]}
            lineWidth={1.5}
            opacity={opacity}
            transparent
            dashed={dashMap[rel.type]}
            dashSize={0.3}
            gapSize={0.2}
          />
        );
      })}
    </group>
  );
}

function RoleDecoration({ role, alive }: { role: string; alive: boolean }) {
  const opacity = alive ? 0.88 : 0.3;

  switch (role) {
    case "间谍":
    case "狼人":
      // 黑色兜帽 + 浮动匕首
      return (
        <group>
          <mesh position={[0, 0.92, 0]}>
            <coneGeometry args={[0.32, 0.28, 6]} />
            <meshStandardMaterial color="#1a0a2e" emissive="#f05cff" emissiveIntensity={0.2} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0.42, 0.6, 0]} rotation={[0, 0, -Math.PI / 4]}>
            <coneGeometry args={[0.05, 0.36, 4]} />
            <meshStandardMaterial color="#c0c0c0" emissive="#f05cff" emissiveIntensity={0.15} metalness={0.8} roughness={0.1} transparent opacity={opacity} />
          </mesh>
        </group>
      );

    case "CEO":
      // 金色皇冠
      return (
        <group position={[0, 0.96, 0]}>
          <mesh>
            <cylinderGeometry args={[0.24, 0.28, 0.12, 5]} />
            <meshStandardMaterial color="#f8c47a" emissive="#ffd700" emissiveIntensity={0.4} metalness={0.7} roughness={0.15} transparent opacity={opacity} />
          </mesh>
          {[0, 1, 2, 3, 4].map((i) => {
            const a = (Math.PI * 2 * i) / 5;
            return (
              <mesh key={i} position={[Math.cos(a) * 0.22, 0.12, Math.sin(a) * 0.22]}>
                <coneGeometry args={[0.04, 0.14, 4]} />
                <meshStandardMaterial color="#ffd700" emissive="#ffd700" emissiveIntensity={0.5} metalness={0.8} roughness={0.1} transparent opacity={opacity} />
              </mesh>
            );
          })}
        </group>
      );

    case "HR总监":
      // 浮动文件夹/公文包
      return (
        <group position={[-0.44, 0.5, 0]} rotation={[0, 0.3, 0.15]}>
          <mesh>
            <boxGeometry args={[0.28, 0.36, 0.06]} />
            <meshStandardMaterial color="#4dc7ff" emissive="#4dc7ff" emissiveIntensity={0.25} metalness={0.3} roughness={0.4} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0, 0.16, 0.02]}>
            <boxGeometry args={[0.14, 0.04, 0.08]} />
            <meshStandardMaterial color="#bdf4ff" metalness={0.5} roughness={0.2} transparent opacity={opacity} />
          </mesh>
        </group>
      );

    case "安保主管":
      // 盾牌
      return (
        <group position={[0.44, 0.4, 0]} rotation={[0, -0.4, 0]}>
          <mesh>
            <cylinderGeometry args={[0.22, 0.16, 0.06, 6]} />
            <meshStandardMaterial color="#8b5cf6" emissive="#8b5cf6" emissiveIntensity={0.3} metalness={0.6} roughness={0.2} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0, 0, 0.04]}>
            <cylinderGeometry args={[0.08, 0.08, 0.02, 4]} />
            <meshStandardMaterial color="#bdf4ff" emissive="#ffffff" emissiveIntensity={0.2} transparent opacity={opacity} />
          </mesh>
        </group>
      );

    case "法务总监":
      // 天平符号
      return (
        <group position={[0, 1.12, 0]}>
          <mesh>
            <cylinderGeometry args={[0.015, 0.015, 0.5, 8]} />
            <meshStandardMaterial color="#4de7db" emissive="#4de7db" emissiveIntensity={0.3} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0, 0.25, 0]} rotation={[0, 0, 0]}>
            <boxGeometry args={[0.48, 0.025, 0.025]} />
            <meshStandardMaterial color="#4de7db" emissive="#4de7db" emissiveIntensity={0.3} transparent opacity={opacity} />
          </mesh>
          {[-1, 1].map((side) => (
            <mesh key={side} position={[side * 0.22, 0.18, 0]}>
              <sphereGeometry args={[0.06, 12, 12]} />
              <meshStandardMaterial color="#4de7db" emissive="#4de7db" emissiveIntensity={0.4} transparent opacity={opacity} />
            </mesh>
          ))}
        </group>
      );

    case "普通员工":
      // 领带
      return (
        <group position={[0, 0.15, 0.32]}>
          <mesh>
            <boxGeometry args={[0.07, 0.22, 0.02]} />
            <meshStandardMaterial color="#56e3ff" emissive="#56e3ff" emissiveIntensity={0.15} transparent opacity={opacity} />
          </mesh>
          <mesh position={[0, -0.13, 0]}>
            <coneGeometry args={[0.055, 0.1, 3]} />
            <meshStandardMaterial color="#56e3ff" emissive="#56e3ff" emissiveIntensity={0.15} transparent opacity={opacity} />
          </mesh>
        </group>
      );

    default:
      return null;
  }
}

function ArenaFloor() {
  return (
    <group>
      {/* 办公室地面 - 深色大理石质感 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.62, 0]}>
        <circleGeometry args={[8.5, 6]} />
        <meshStandardMaterial color="#0a0f1a" metalness={0.3} roughness={0.7} />
      </mesh>
      {/* 地面方格网线 - 办公室地砖感 */}
      {Array.from({ length: 13 }, (_, i) => i - 6).map((offset) => (
        <group key={`grid-${offset}`}>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[offset * 1.1, -0.6, 0]}>
            <planeGeometry args={[0.01, 14]} />
            <meshBasicMaterial color="#1a3a5c" transparent opacity={0.18} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, Math.PI / 2, 0]} position={[0, -0.6, offset * 1.1]}>
            <planeGeometry args={[0.01, 14]} />
            <meshBasicMaterial color="#1a3a5c" transparent opacity={0.18} />
          </mesh>
        </group>
      ))}
      {/* 会议桌 - 椭圆玻璃桌面 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.2, 0]}>
        <circleGeometry args={[5.2, 80]} />
        <meshStandardMaterial color="#0c1e30" metalness={0.85} roughness={0.08} transparent opacity={0.82} />
      </mesh>
      {/* 桌面边缘 - 金属镶边 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.19, 0]}>
        <ringGeometry args={[5.1, 5.25, 80]} />
        <meshStandardMaterial color="#4dc7ff" emissive="#4dc7ff" emissiveIntensity={0.3} metalness={0.9} roughness={0.1} />
      </mesh>
      {/* 桌腿 - 四根柱体 */}
      {[0, Math.PI / 2, Math.PI, Math.PI * 1.5].map((angle) => (
        <mesh key={`leg-${angle}`} position={[Math.cos(angle) * 3.8, -0.42, Math.sin(angle) * 3.8]}>
          <cylinderGeometry args={[0.06, 0.08, 0.44, 16]} />
          <meshStandardMaterial color="#2a4a6a" metalness={0.8} roughness={0.2} />
        </mesh>
      ))}
      {/* 中央投影柱底座 */}
      <mesh position={[0, -0.18, 0]}>
        <cylinderGeometry args={[0.7, 0.85, 0.08, 64]} />
        <meshStandardMaterial color="#0f2a40" emissive="#4dc7ff" emissiveIntensity={0.15} metalness={0.7} roughness={0.2} />
      </mesh>
      {/* 中央全息投影柱 */}
      <mesh position={[0, 0.5, 0]}>
        <cylinderGeometry args={[0.08, 0.08, 1.2, 24]} />
        <meshStandardMaterial color="#1a4a6a" emissive="#4dc7ff" emissiveIntensity={0.6} transparent opacity={0.5} metalness={0.4} roughness={0.1} />
      </mesh>
      {/* 全息投影光环 */}
      {[0.3, 0.6, 0.9].map((y) => (
        <mesh key={`holo-${y}`} rotation={[-Math.PI / 2, 0, 0]} position={[0, y, 0]}>
          <ringGeometry args={[0.2, 0.35, 32]} />
          <meshBasicMaterial color="#4dc7ff" transparent opacity={0.2 + y * 0.15} />
        </mesh>
      ))}
      {/* 顶部全息球 - 公司logo意象 */}
      <mesh position={[0, 1.2, 0]}>
        <dodecahedronGeometry args={[0.32, 0]} />
        <meshStandardMaterial color="#0a75a8" emissive="#22d3ee" emissiveIntensity={0.8} transparent opacity={0.6} metalness={0.2} roughness={0.1} wireframe />
      </mesh>
      <mesh position={[0, 1.2, 0]}>
        <dodecahedronGeometry args={[0.2, 0]} />
        <meshStandardMaterial color="#4dc7ff" emissive="#4dc7ff" emissiveIntensity={1.0} transparent opacity={0.4} />
      </mesh>
      {/* 座位编号标记环 */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.17, 0]}>
        <ringGeometry args={[4.0, 4.05, 80]} />
        <meshBasicMaterial color="#4dc7ff" transparent opacity={0.35} />
      </mesh>
      <pointLight position={[0, 2.0, 0]} intensity={1.8} color="#22d3ee" />
      <pointLight position={[0, -0.1, 0]} intensity={0.6} color="#4dc7ff" />
      {/* 场景装饰 - 办公环境 */}
      <OfficeProps />
    </group>
  );
}

function OfficeProps() {
  return (
    <group>
      {/* 背景墙 - 弧形玻璃幕墙 */}
      <mesh position={[0, 1.5, -7.5]} rotation={[0, 0, 0]}>
        <planeGeometry args={[16, 5]} />
        <meshStandardMaterial color="#050d18" metalness={0.9} roughness={0.05} transparent opacity={0.4} />
      </mesh>
      {/* 幕墙横线 */}
      {[-0.5, 0.8, 2.1, 3.4].map((y) => (
        <mesh key={`wall-line-${y}`} position={[0, y, -7.48]}>
          <planeGeometry args={[16, 0.015]} />
          <meshBasicMaterial color="#4dc7ff" transparent opacity={0.2} />
        </mesh>
      ))}
      {/* 白板 */}
      <group position={[-7.2, 1.4, -3]}>
        <mesh>
          <boxGeometry args={[0.08, 2.2, 1.6]} />
          <meshStandardMaterial color="#e8edf2" metalness={0.1} roughness={0.8} />
        </mesh>
        <mesh position={[0.05, 0, 0]}>
          <boxGeometry args={[0.02, 2.0, 1.4]} />
          <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.05} />
        </mesh>
        {/* 白板上的便利贴 */}
        {[[-0.4, 0.5], [0.1, 0.3], [-0.2, -0.3], [0.3, -0.1]].map(([oy, oz], i) => (
          <mesh key={`note-${i}`} position={[0.06, oy!, oz!]}>
            <planeGeometry args={[0.22, 0.22]} />
            <meshBasicMaterial color={["#f8c47a", "#4dc7ff", "#ff4f87", "#4de7db"][i]} transparent opacity={0.7} />
          </mesh>
        ))}
      </group>
      {/* 书架 */}
      <group position={[7.2, 0.6, -2]}>
        <mesh>
          <boxGeometry args={[0.12, 2.8, 1.2]} />
          <meshStandardMaterial color="#1a2a3a" metalness={0.4} roughness={0.6} />
        </mesh>
        {/* 书本 */}
        {[-0.8, -0.2, 0.4, 1.0].map((shelfY) => (
          <group key={`shelf-${shelfY}`} position={[-0.02, shelfY, 0]}>
            {Array.from({ length: 5 }, (_, i) => (
              <mesh key={i} position={[0.04, 0.12, (i - 2) * 0.2]}>
                <boxGeometry args={[0.12, 0.22 + Math.random() * 0.06, 0.14]} />
                <meshStandardMaterial color={["#2a4a7a", "#4a2a5a", "#1a4a4a", "#5a3a2a", "#2a3a5a"][i]} metalness={0.2} roughness={0.7} />
              </mesh>
            ))}
          </group>
        ))}
      </group>
      {/* 绿植 - 落地盆栽 */}
      {[[-6.5, -0.3, 3.5], [6.5, -0.3, 3.5]].map(([px, py, pz], i) => (
        <group key={`plant-${i}`} position={[px!, py!, pz!]}>
          <mesh position={[0, 0, 0]}>
            <cylinderGeometry args={[0.25, 0.2, 0.5, 16]} />
            <meshStandardMaterial color="#2a2a2a" metalness={0.3} roughness={0.8} />
          </mesh>
          <mesh position={[0, 0.5, 0]}>
            <sphereGeometry args={[0.45, 16, 12]} />
            <meshStandardMaterial color="#1a5a2a" emissive="#0a3a1a" emissiveIntensity={0.2} roughness={0.9} />
          </mesh>
          <mesh position={[0.15, 0.75, 0.1]}>
            <sphereGeometry args={[0.25, 12, 10]} />
            <meshStandardMaterial color="#2a6a3a" roughness={0.9} />
          </mesh>
        </group>
      ))}
      {/* 饮水机 */}
      <group position={[7, -0.1, 2.5]}>
        <mesh position={[0, 0.4, 0]}>
          <boxGeometry args={[0.35, 1.2, 0.3]} />
          <meshStandardMaterial color="#e0e4e8" metalness={0.4} roughness={0.3} />
        </mesh>
        <mesh position={[0, 1.1, 0]}>
          <cylinderGeometry args={[0.16, 0.16, 0.4, 20]} />
          <meshStandardMaterial color="#4dc7ff" transparent opacity={0.35} metalness={0.1} roughness={0.1} />
        </mesh>
      </group>
      {/* 落地窗外的城市天际线意象 */}
      {Array.from({ length: 10 }, (_, i) => {
        const bx = (i - 4.5) * 1.5;
        const bh = 1.0 + Math.sin(i * 2.3) * 0.8;
        return (
          <mesh key={`skyline-${i}`} position={[bx, bh / 2 + 2.5, -7.6]}>
            <boxGeometry args={[0.8, bh, 0.1]} />
            <meshBasicMaterial color="#0a1a2a" transparent opacity={0.5} />
          </mesh>
        );
      })}
      {/* 建筑物窗户光点 */}
      {Array.from({ length: 20 }, (_, i) => {
        const bx = (Math.floor(i / 2) - 4.5) * 1.5 + (i % 2 === 0 ? -0.15 : 0.15);
        const by = 2.6 + Math.sin(i * 1.7) * 0.5;
        return (
          <mesh key={`win-${i}`} position={[bx, by, -7.55]}>
            <planeGeometry args={[0.12, 0.08]} />
            <meshBasicMaterial color="#f8c47a" transparent opacity={0.3 + (i % 3) * 0.15} />
          </mesh>
        );
      })}
    </group>
  );
}

export const ArenaStage = memo(function ArenaStage({ players, currentEvent, viewMode, selectedSeat, events = [], onBubbleClick }: ArenaStageProps) {
  const isNight = currentEvent.phase?.includes("夜");
  const [webglAvailable] = useState(() => canUseWebGL());
  const [mounted, setMounted] = useState(false);

  const teammates = useMemo(() => {
    const me = players.find((p) => p.seat === selectedSeat);
    if (!me || me.faction !== "间谍") return [];
    return players.filter((p) => p.faction === "间谍" && p.seat !== selectedSeat).map((p) => p.seat);
  }, [players, selectedSeat]);

  useEffect(() => { setMounted(true); }, []);

  if (!mounted || !webglAvailable) {
    return <ArenaStageFallback players={players} currentEvent={currentEvent} viewMode={viewMode} selectedSeat={selectedSeat} events={events} reason={mounted ? "webgl" : "loading"} />;
  }

  return (
    <CanvasErrorBoundary players={players} currentEvent={currentEvent} viewMode={viewMode} selectedSeat={selectedSeat} onBubbleClick={onBubbleClick}>
      <div className="hud-stage relative h-full min-h-[560px] w-full overflow-hidden">
        <Canvas className="h-full w-full" style={{ width: "100%", height: "100%" }} shadows dpr={[1, 1.6]}>
          <PerspectiveCamera makeDefault position={[0, 6.9, 7.7]} fov={48} />
          <color attach="background" args={[isNight ? "#020813" : "#06111f"]} />
          <ambientLight intensity={0.42} />
          <directionalLight position={[3, 6, 4]} intensity={1.4} castShadow />
          <pointLight position={[0, 4, 1]} intensity={1.1} color="#4dc7ff" />
          <ArenaFloor />
          {players.map((player, index) => (
            <SeatNode
              key={player.seat}
              player={player}
              index={index}
              total={players.length}
              currentEvent={currentEvent}
              viewMode={viewMode}
              selectedSeat={selectedSeat}
              teammates={teammates}
              onBubbleClick={onBubbleClick}
            />
          ))}
          <ActionBeam players={players} currentEvent={currentEvent} />
          <RelationshipLines players={players} events={events} />
          <OrbitControls enablePan={false} minDistance={7} maxDistance={11} maxPolarAngle={Math.PI / 2.08} />
        </Canvas>
        <div className="absolute right-5 top-5 rounded-md border border-cyan/20 bg-slate-950/70 p-3 text-xs text-slate-300">
          <div className="mb-2 flex items-center gap-2"><span className="h-px w-8 bg-cyan" />信任关系</div>
          <div className="mb-2 flex items-center gap-2"><span className="h-px w-8 bg-danger" />怀疑关系</div>
          <div className="flex items-center gap-2"><span className="h-px w-8 border-t border-dashed border-gold" />信息交互</div>
        </div>
      </div>
    </CanvasErrorBoundary>
  );
});

export function canUseWebGL(targetDocument: Document | undefined = typeof document === "undefined" ? undefined : document): boolean {
  if (!targetDocument) return false;

  try {
    const canvas = targetDocument.createElement("canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
    if (!gl) return false;
    // Verify context is not lost
    if ("isContextLost" in gl && (gl as WebGLRenderingContext).isContextLost()) return false;
    return true;
  } catch {
    return false;
  }
}
