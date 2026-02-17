import React from 'react'
import { createRoot } from 'react-dom/client'
import { createHashRouter, RouterProvider } from 'react-router-dom'
import './styles.css'
import App from './shell/App'
import Dashboard from './views/Dashboard'
import Wallet from './views/Wallet'
import DAO from './views/DAO'
import Subscriptions from './views/Subscriptions'
import NFTs from './views/NFTs'
import Market from './views/Market'
import Models from './views/Models'
import Interchain from './views/Interchain'
import CoinJoin from './views/CoinJoin'
import Vaults from './views/Vaults'
import Settings from './views/Settings'

const router = createHashRouter([
  { path: '/', element: <App />, children: [
    { index: true, element: <Dashboard/> },
    { path: 'wallet', element: <Wallet/> },
    { path: 'coinjoin', element: <CoinJoin/> },
    { path: 'vaults', element: <Vaults/> },
    { path: 'dao', element: <DAO/> },
    { path: 'interchain', element: <Interchain/> },
    { path: 'ai', element: <Models/> },
    { path: 'market', element: <Market/> },
    { path: 'models', element: <Models/> },
    { path: 'subscriptions', element: <Subscriptions/> },
    { path: 'nfts', element: <NFTs/> },
    { path: 'settings', element: <Settings/> }
  ]}
])

createRoot(document.getElementById('root')!).render(<RouterProvider router={router}/>)
