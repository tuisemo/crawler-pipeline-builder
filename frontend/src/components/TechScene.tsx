import { useEffect, useRef } from 'react'
import * as THREE from 'three'

export const TechScene = () => {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Clean up container
    containerRef.current.innerHTML = ''

    const width = 720
    const height = 720
    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0xffffff, 0.05)

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    
    renderer.setSize(width, height)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    containerRef.current.appendChild(renderer.domElement)

    const mainGroup = new THREE.Group()

    // --- 1. Core Data Matrix (Enlarged) ---
    const cubeGroup = new THREE.Group()
    const cubes: { mesh: THREE.Mesh; originalPos: THREE.Vector3; targetOffset: THREE.Vector3 }[] = []
    const cubeGeo = new THREE.BoxGeometry(0.28, 0.28, 0.28)
    
    for (let x = -1; x <= 1; x++) {
      for (let y = -1; y <= 1; y++) {
        for (let z = -1; z <= 1; z++) {
          const isCore = x === 0 && y === 0 && z === 0
          const mat = new THREE.MeshPhongMaterial({
            color: isCore ? 0x000000 : (Math.abs(x + y + z) % 2 === 0 ? 0x007aff : 0x000000),
            emissive: isCore ? 0x007aff : (Math.abs(x + y + z) % 2 === 0 ? 0x002244 : 0x000000),
            transparent: true,
            opacity: 0.8,
          })
          const cube = new THREE.Mesh(cubeGeo, mat)
          const pos = new THREE.Vector3(x * 0.52, y * 0.52, z * 0.52)
          cube.position.copy(pos)
          cubeGroup.add(cube)
          cubes.push({ mesh: cube, originalPos: pos, targetOffset: new THREE.Vector3(0, 0, 0) })
        }
      }
    }
    mainGroup.add(cubeGroup)

    // --- 2. Planet Skeleton ---
    const skeletonGeo = new THREE.IcosahedronGeometry(2.8, 2)
    const skeletonMat = new THREE.MeshPhongMaterial({
      color: 0x007aff,
      wireframe: true,
      transparent: true,
      opacity: 0.06,
    })
    const skeleton = new THREE.Mesh(skeletonGeo, skeletonMat)
    mainGroup.add(skeleton)

    // --- 3. Tech Rings ---
    const ringMat = new THREE.MeshPhongMaterial({ color: 0x007aff, transparent: true, opacity: 0.04 })
    const ring1 = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.005, 16, 100), ringMat)
    const ring2 = new THREE.Mesh(new THREE.TorusGeometry(3.6, 0.005, 16, 100), ringMat)
    ring2.rotation.x = Math.PI / 2
    mainGroup.add(ring1)
    mainGroup.add(ring2)

    // --- 4. Floating 2D Shards ---
    const shardGroup = new THREE.Group()
    const shards: THREE.Mesh[] = []
    const shardGeo = new THREE.PlaneGeometry(0.25, 0.25)
    const blueMat = new THREE.MeshBasicMaterial({ color: 0x007aff, transparent: true, opacity: 0.25, side: THREE.DoubleSide })
    const blackMat = new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.2, side: THREE.DoubleSide })

    for (let i = 0; i < 35; i++) {
      const mesh = new THREE.Mesh(shardGeo, Math.random() > 0.5 ? blueMat : blackMat)
      mesh.position.set((Math.random() - 0.5) * 15, (Math.random() - 0.5) * 15, (Math.random() - 0.5) * 15)
      mesh.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, Math.random() * Math.PI)
      mesh.userData = { 
        vel: new THREE.Vector3((Math.random() - 0.5) * 0.02, (Math.random() - 0.5) * 0.02, (Math.random() - 0.5) * 0.02),
        rot: new THREE.Vector3(Math.random() * 0.015, Math.random() * 0.015, Math.random() * 0.015)
      }
      shards.push(mesh)
      shardGroup.add(mesh)
    }
    scene.add(shardGroup)

    scene.add(mainGroup)

    // --- Lights ---
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2)
    scene.add(ambientLight)
    const pointLight = new THREE.PointLight(0x007aff, 20, 60)
    pointLight.position.set(10, 10, 10)
    scene.add(pointLight)

    camera.position.z = 8.5 // Closer for more impact

    // --- Interaction ---
    let targetX = 0, targetY = 0, curX = 0, curY = 0
    const onMouseMove = (e: MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (rect) {
        targetX = ((e.clientX - rect.left) / width - 0.5) * 2
        targetY = ((e.clientY - rect.top) / height - 0.5) * 2
      }
    }
    window.addEventListener('mousemove', onMouseMove)

    // --- Reconstitution Cycle ---
    let phase = 0, timer = 0
    const cycleLogic = (dt: number) => {
      timer += dt
      if (timer > 10) { 
        phase = 1; timer = 0; 
        cubes.forEach(c => c.targetOffset.set((Math.random() - 0.5) * 0.8, (Math.random() - 0.5) * 0.8, (Math.random() - 0.5) * 0.8)) 
      }
      if (phase === 1 && timer > 3) phase = 2
      if (phase === 2 && timer > 4.5) { phase = 0; timer = 0 }
      
      cubes.forEach(c => {
        const target = phase === 1 ? c.originalPos.clone().add(c.targetOffset) : c.originalPos
        c.mesh.position.lerp(target, phase === 0 ? 0.1 : 0.05)
      })
    }

    // --- Animation ---
    const animate = () => {
      const id = requestAnimationFrame(animate)
      curX += (targetX - curX) * 0.05
      curY += (targetY - curY) * 0.05

      cycleLogic(0.016)

      // Slow & Static Rotation
      skeleton.rotation.y += 0.0002
      ring1.rotation.y += 0.0003
      ring2.rotation.z -= 0.0002
      cubeGroup.rotation.y += 0.0001 + curX * 0.015
      cubeGroup.rotation.x += 0.0001 + curY * 0.015

      // Shard Drifting
      shards.forEach(m => {
        m.position.add(m.userData.vel)
        m.rotation.x += m.userData.rot.x
        m.rotation.y += m.userData.rot.y
        if (Math.abs(m.position.x) > 10) m.position.x *= -0.95
        if (Math.abs(m.position.y) > 10) m.position.y *= -0.95
        if (Math.abs(m.position.z) > 10) m.position.z *= -0.95
      })

      mainGroup.rotation.y = curX * 0.06
      mainGroup.rotation.x = -curY * 0.06

      renderer.render(scene, camera)
      return id
    }
    const animId = animate()

    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      cancelAnimationFrame(animId)
      if (containerRef.current) containerRef.current.innerHTML = ''
      renderer.dispose()
    }
  }, [])

  return (
    <div ref={containerRef} style={{ width: 720, height: 720, display: 'flex', justifyContent: 'center', alignItems: 'center', cursor: 'grab' }} />
  )
}
