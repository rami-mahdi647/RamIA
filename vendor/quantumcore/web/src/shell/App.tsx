import React from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { BuildFooter } from '../components/BuildFooter'

const NavItem = ({to, children}:{to:string, children:React.ReactNode}) => (
  <NavLink to={to} className={({isActive}) =>
    `block m-2 px-3 py-2 rounded-lg ${isActive? 'bg-[#1a2342] text-white':'bg-[#141a2e] text-[#cbd6ff]'}`}>
    {children}
  </NavLink>
)

export default function App(){
  return (
    <div className="min-h-screen flex">
      <aside className="w-64 bg-[#0f1322] border-r border-[#1a2033] flex flex-col">
        <div className="p-6 font-extrabold text-2xl bg-gradient-to-r from-blue-600 to-sky-400 bg-clip-text text-transparent">
          QuantumCore
        </div>
        <nav className="px-2">
          <NavItem to="/">Dashboard</NavItem>
          <NavItem to="/wallet">Wallet</NavItem>
          <NavItem to="/coinjoin">CoinJoin</NavItem>
          <NavItem to="/vaults">Vaults & Minería</NavItem>
          <NavItem to="/dao">DAO</NavItem>
          <NavItem to="/interchain">Interchain</NavItem>
          <NavItem to="/market">Market Sentinel</NavItem>
          <NavItem to="/models">Model Lab</NavItem>
          <NavItem to="/subscriptions">Subscriptions</NavItem>
          <NavItem to="/nfts">NFTs</NavItem>
          <NavItem to="/settings">Settings</NavItem>
        </nav>
        <div className="mt-auto p-5 text-[#9fb3ff] text-xs opacity-80">Predict • Outpace • Win</div>
      </aside>
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="flex items-center justify-between px-6 py-4 border-b border-[#1a2033] bg-gradient-to-b from-[#0f1322] to-[#0b0e16]">
          <div className="text-lg text-[#dce6ff]">QuantumCore</div>
        </header>
        <section className="p-6 flex-1">
          <Outlet/>
        </section>
        <BuildFooter />
      </main>
    </div>
  )
}