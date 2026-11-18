import unittest
import cv2
import numpy as np
from green_wall_mapper import masks, floor_tracks, Mapper, camera_axes, camera_geometry, relative_pose, axes_for_floor_normal, K, D


class GeometryTests(unittest.TestCase):
    def test_floor_tracking_known_motion(self):
        rng=np.random.default_rng(405)
        a=np.zeros((480,640),np.uint8)
        for x,y in rng.integers([30,40],[610,440],size=(300,2)):
            cv2.circle(a,(int(x),int(y)),2,200,-1)
        truth=np.array([[1.,.002,7.],[.001,1.,-4.],[.00001,-.00002,1.]])
        b=cv2.warpPerspective(a,truth,(640,480));mask=np.full_like(a,255)
        found,info=floor_tracks(a,b,mask,mask)
        self.assertIsNotNone(found,info)
        probe=np.float32([[[100,100]],[[500,350]],[[320,240]]])
        actual=cv2.perspectiveTransform(probe,found[0])
        expected=cv2.perspectiveTransform(probe,truth)
        self.assertLess(float(np.max(np.linalg.norm(actual-expected,axis=2))),.5)

    def test_green_needs_visible_floor_contact(self):
        image=np.zeros((480,640,3),np.uint8);image[:]=(20,80,20)
        self.assertEqual(len(masks(image)[2]),0)
        image[280:]=(140,140,140)
        green,floor,contact=masks(image)
        self.assertGreater(len(contact),500)
        self.assertEqual(int(floor[:280].sum()),0)
        self.assertGreater(int(floor[310:].sum()),0)
        gray=np.full_like(image,140)
        self.assertEqual(len(masks(gray)[2]),0)

    def test_tracking_loss_freezes_map_and_nominal_axes(self):
        axes=camera_axes()
        np.testing.assert_allclose(axes.T@axes,np.eye(3),atol=1e-12)
        self.assertGreater(float(np.linalg.det(axes)),.999)
        image=np.full((480,640,3),140,np.uint8);image[:280]=(20,80,20)
        mapper=Mapper();mapper.update(image);before=len(mapper.boundaries)
        mapper.update(image)
        self.assertTrue(mapper.lost)
        mapper.update(image)
        self.assertEqual(len(mapper.boundaries),before)

    def test_pose_with_known_floor_motion_and_camera_offset(self):
        origin,axes=camera_geometry();offset=origin/origin[2]
        angle=.025
        rb=np.array([[np.cos(angle),-np.sin(angle),0],
                     [np.sin(angle),np.cos(angle),0],[0,0,1.]])
        body_delta=np.array([.12,-.03,0.])
        camera_delta=body_delta+(rb-np.eye(3))@offset
        r=axes.T@rb.T@axes;t=-r@axes.T@camera_delta
        n=-axes.T@np.array([0.,0.,1.])
        h=K@(r+np.outer(t,n))@np.linalg.inv(K)
        pose,status=relative_pose(h,axes,offset)
        self.assertIsNotNone(pose,status)
        np.testing.assert_allclose([pose['x'],pose['y']],body_delta[:2],atol=1e-8)
        self.assertAlmostEqual(pose['yaw_deg'],float(np.degrees(angle)),places=6)

    def test_fisheye_ray_roundtrip_before_pose_estimation(self):
        y,x=np.mgrid[-.3:.31:.1,-.4:.41:.1]
        rays=np.c_[x.ravel(),y.ravel()].reshape(-1,1,2)
        raw=cv2.fisheye.distortPoints(rays,K,D)
        recovered=cv2.fisheye.undistortPoints(raw,K,D)
        np.testing.assert_allclose(recovered,rays,atol=1e-8)

    def test_visual_floor_frame_and_normal_consensus(self):
        from fit_floor_normal import fit
        n=np.array([.02,.67,.74]);n/=np.linalg.norm(n)
        axes=axes_for_floor_normal(n)
        np.testing.assert_allclose(axes@n,[0,0,-1.],atol=1e-12)
        np.testing.assert_allclose(axes@axes.T,np.eye(3),atol=1e-12)
        views=[dict(to_anchor=np.eye(3).tolist(),view=0)]
        for i,t in enumerate([[-.05,.003,0.],[.01,.06,0.],[-.12,-.03,0.]]):
            t=np.array(t);h=K@(np.eye(3)+np.outer(t,n))@np.linalg.inv(K)
            views.append(dict(to_anchor=np.linalg.inv(h).tolist(),view=i+1))
        result=fit(dict(views=views))
        self.assertEqual(result['views_supporting'],3)
        np.testing.assert_allclose(result['floor_normal_camera'],n,atol=1e-8)


if __name__=='__main__':unittest.main()
